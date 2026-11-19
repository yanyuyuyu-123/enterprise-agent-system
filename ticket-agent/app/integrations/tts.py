"""CosyVoice2 适配：语音合成、超时与失败降级。

只负责把文本转成 wav 文件，不读写数据库、不判断权限。
"""

from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings
from app.core.errors import AppError


def _synthesize_once(text: str, voice: str, target: Path, timeout: float) -> None:
    url = f"{settings.cosyvoice_base_url.rstrip('/')}/tts"
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            data={"text": text, "speaker": voice or settings.cosyvoice_speaker},
        )
        response.raise_for_status()

    content = response.content
    if not content or content[:4] != b"RIFF" or content[8:12] != b"WAVE":
        raise RuntimeError("CosyVoice2 返回的音频格式不正确")
    target.write_bytes(content)


def synthesize(text: str, target: Path, *, voice: str) -> None:
    """单次超时后重试 1 次；仍失败抛 4000，由前端降级为纯文字。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    timeout = float(settings.voice_tts_timeout_seconds)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            _synthesize_once(text, voice, target, timeout)
            if target.is_file() and target.stat().st_size > 0:
                return
            last_error = RuntimeError("语音合成结果为空")
        except Exception as exc:  # noqa: BLE001 - 外部服务异常统一降级
            last_error = exc
            target.unlink(missing_ok=True)
    raise AppError(4000, "语音播报暂不可用，请查看文字回答", 502) from last_error
