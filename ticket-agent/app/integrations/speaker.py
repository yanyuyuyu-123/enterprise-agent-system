"""声纹：CAM++ 说话人向量提取与相似度比对。

只做本人校验，不作为身份认证手段；模型缺失时调用方应降级为「不校验」。
"""

from __future__ import annotations

import array
import math
import sys
from pathlib import Path
from typing import Any

from app.core.config import settings

ENGINE = "campplus-zh-16k"
_CACHE: dict[str, Any] = {"extractor": None, "failed": False}


def is_configured() -> bool:
    path = settings.voice_sv_model.strip()
    return bool(path) and Path(path).is_file()


def _get_extractor() -> Any:
    if _CACHE["extractor"] is not None or _CACHE["failed"]:
        return _CACHE["extractor"]
    if not is_configured():
        return None
    try:
        import sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=settings.voice_sv_model,
            num_threads=1,
            debug=False,
            provider="cpu",
        )
        _CACHE["extractor"] = sherpa_onnx.SpeakerEmbeddingExtractor(config)
    except Exception:
        _CACHE["failed"] = True
        return None
    return _CACHE["extractor"]


def has_speech(pcm: bytes) -> bool:
    """粗略判断这段录音里有没有人声：至少 5% 的 20ms 帧能量超过阈值。

    只为挡住「没说话却录入」的静音片段，不做精细 VAD。
    """
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    frame = 320
    total = 0
    voiced = 0
    for start in range(0, len(samples) - frame + 1, frame):
        chunk = samples[start : start + frame]
        energy = math.fsum(value * value for value in chunk) / frame
        total += 1
        if math.sqrt(energy) / 32768.0 > 0.008:
            voiced += 1
    if total == 0:
        return False
    return voiced >= 5 and voiced / total >= 0.05


def embed(pcm: bytes) -> list[float] | None:
    """16kHz/16bit 单声道 PCM → 归一化 192 维声纹向量。"""
    extractor = _get_extractor()
    if extractor is None:
        return None
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    if len(samples) < 16000 * 0.5:
        return None
    waveform = [value / 32768.0 for value in samples]
    stream = extractor.create_stream()
    stream.accept_waveform(16000, waveform)
    stream.input_finished()
    if not extractor.is_ready(stream):
        return None
    vector = list(extractor.compute(stream))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return None
    return [value / norm for value in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


def average(vectors: list[list[float]]) -> list[float]:
    size = len(vectors[0])
    merged = [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]
    norm = math.sqrt(sum(value * value for value in merged))
    if norm <= 0:
        raise ValueError("empty embedding")
    return [value / norm for value in merged]
