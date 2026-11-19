"""本地语音识别适配：WAV 校验、VAD 切段、SenseVoice int8 推理。

只做推理，不读写数据库、不判断权限。模型按需懒加载并在进程内复用。
"""

from __future__ import annotations

import io
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import AppError

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
MAX_SEGMENT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class WavInfo:
    duration_ms: int
    channels: int
    sample_rate: int
    sample_width: int
    pcm: bytes


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str


_lock = threading.Lock()
_recognizer: Any | None = None


def read_wav(data: bytes) -> WavInfo:
    """只接受 16kHz/16bit/单声道 WAV；格式不符直接 1001。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            sample_width = reader.getsampwidth()
            frames = reader.getnframes()
            pcm = reader.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise AppError(1001, "只支持 WAV 格式的录音", 400) from exc

    if sample_rate != SAMPLE_RATE or sample_width != SAMPLE_WIDTH or channels != 1:
        raise AppError(1001, "录音须为 16kHz/16bit/单声道 WAV", 400)

    duration_ms = int(frames / sample_rate * 1000) if sample_rate else 0
    return WavInfo(
        duration_ms=duration_ms,
        channels=channels,
        sample_rate=sample_rate,
        sample_width=sample_width,
        pcm=pcm,
    )


def _model_paths() -> tuple[Path, Path]:
    model_dir = Path(settings.voice_asr_model_dir) if settings.voice_asr_model_dir else None
    if model_dir is None:
        raise AppError(5002, "语音识别模型未配置", 500)
    model = model_dir / "model.int8.onnx"
    tokens = model_dir / "tokens.txt"
    if not model.is_file() or not tokens.is_file():
        raise AppError(5002, "语音识别模型文件缺失", 500)
    return model, tokens


def _get_recognizer() -> Any:
    global _recognizer
    if _recognizer is not None:
        return _recognizer
    with _lock:
        if _recognizer is not None:
            return _recognizer
        model, tokens = _model_paths()
        try:
            import sherpa_onnx
        except ImportError as exc:  # pragma: no cover - 依赖缺失时仅语音不可用
            raise AppError(5002, "语音识别依赖未安装", 500) from exc

        _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model),
            tokens=str(tokens),
            num_threads=settings.voice_asr_threads,
            use_itn=True,
            language="zh",
        )
        return _recognizer


def _to_floats(pcm: bytes) -> Any:
    """16bit PCM 转 [-1, 1] 的 float32 数组，sherpa-onnx 只接受浮点采样。"""
    import numpy as np

    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _split_fixed(samples: Any) -> list[tuple[int, int, Any]]:
    """无 VAD 模型时按固定 30 秒窗口切段，保证单段不超过上限。"""
    chunk = SAMPLE_RATE * MAX_SEGMENT_SECONDS
    total = len(samples)
    segments: list[tuple[int, int, Any]] = []
    for offset in range(0, total, chunk):
        piece = samples[offset : offset + chunk]
        start_ms = int(offset / SAMPLE_RATE * 1000)
        end_ms = int(min(offset + chunk, total) / SAMPLE_RATE * 1000)
        segments.append((start_ms, end_ms, piece))
    return segments


def _split_by_vad(samples: Any) -> list[tuple[int, int, Any]]:
    """Silero VAD 切段；VAD 模型缺失或调用失败时退回固定窗口。"""
    if not settings.voice_asr_vad_model:
        return _split_fixed(samples)
    vad_path = Path(settings.voice_asr_vad_model)
    if not vad_path.is_file():
        return _split_fixed(samples)
    try:
        import sherpa_onnx
    except ImportError:  # pragma: no cover
        return _split_fixed(samples)

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(vad_path)
    config.silero_vad.min_silence_duration = 0.25
    config.sample_rate = SAMPLE_RATE
    window_size = config.silero_vad.window_size

    try:
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=MAX_SEGMENT_SECONDS)
        segments: list[tuple[int, int, Any]] = []
        cursor = 0
        while cursor < len(samples):
            vad.accept_waveform(samples[cursor : cursor + window_size])
            cursor += window_size
            _drain(vad, segments)
        vad.flush()
        _drain(vad, segments)
    except Exception:  # noqa: BLE001 - VAD 异常不应阻断识别，退回固定窗口
        return _split_fixed(samples)
    return segments or _split_fixed(samples)


def _drain(vad: Any, segments: list[tuple[int, int, Any]]) -> None:
    while not vad.empty():
        segment = vad.front
        start_ms = int(segment.start / SAMPLE_RATE * 1000)
        end_ms = int((segment.start + len(segment.samples)) / SAMPLE_RATE * 1000)
        if end_ms > start_ms:
            segments.append((start_ms, end_ms, segment.samples))
        vad.pop()


def _decode(recognizer: Any, samples: Any) -> str:
    stream = recognizer.create_stream()
    stream.accept_waveform(SAMPLE_RATE, samples)
    recognizer.decode_stream(stream)
    return str(stream.result.text or "").strip()


def transcribe(pcm: bytes) -> list[AsrSegment]:
    """整段 PCM 切段后逐段识别，按顺序拼接的时间戳段落。"""
    recognizer = _get_recognizer()
    samples = _to_floats(pcm)
    results: list[AsrSegment] = []
    with _lock:
        for start_ms, end_ms, piece in _split_by_vad(samples):
            text = _decode(recognizer, piece)
            if text:
                results.append(AsrSegment(start_ms=start_ms, end_ms=end_ms, text=text))
    return results


def transcribe_file(path: Path) -> list[AsrSegment]:
    return transcribe(read_wav(path.read_bytes()).pcm)


def is_configured() -> bool:
    """模型文件齐备才算可用；缺失不影响服务启动与文字链路。"""
    try:
        _model_paths()
    except AppError:
        return False
    return True
