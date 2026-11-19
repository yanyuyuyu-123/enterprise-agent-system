"""音视频转写：复用本地 ASR，输出带时间戳的文本块。

非 WAV 容器借助 ffmpeg 转成 16kHz/16bit/单声道 PCM；未安装 ffmpeg 时明确失败。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.integrations import asr
from app.rag.parser import TextBlock


@dataclass(slots=True)
class TranscribeResult:
    engine: str
    text: str
    duration_ms: int
    segments: list[dict[str, int | str]] = field(default_factory=list)


def _ffmpeg() -> str:
    configured = settings.ffmpeg_bin.strip()
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("ffmpeg")
    if found is None:
        raise AppError(5002, "未安装 ffmpeg，无法解析该音视频格式", 500)
    return found


def _wav_bytes(path: Path, ext: str) -> bytes:
    if ext == "wav":
        return path.read_bytes()
    ffmpeg = _ffmpeg()
    # 输出到临时文件而非管道：管道无法回填 WAV 头，时长会被读成 0x7FFFFFFF
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "audio.wav"
        completed = subprocess.run(  # noqa: S603 - 固定参数调用本机 ffmpeg
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(path),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(target),
            ],
            capture_output=True,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0 or not target.is_file():
            raise AppError(4000, "音视频解码失败", 422)
        return target.read_bytes()


def transcribe_media(path: Path, ext: str) -> tuple[TranscribeResult, list[TextBlock]]:
    if not asr.is_configured():
        raise AppError(5002, "语音识别模型未配置", 500)
    wav = asr.read_wav(_wav_bytes(path, ext))
    segments = asr.transcribe(wav.pcm)
    if not segments:
        raise AppError(3000, "未识别到语音内容", 422)

    blocks = [
        TextBlock(content=segment.text, start_ms=segment.start_ms, end_ms=segment.end_ms)
        for segment in segments
    ]
    result = TranscribeResult(
        engine="sensevoice-small-int8",
        text="".join(segment.text for segment in segments),
        duration_ms=wav.duration_ms,
        segments=[
            {"start_ms": segment.start_ms, "end_ms": segment.end_ms, "text": segment.text}
            for segment in segments
        ],
    )
    return result, blocks
