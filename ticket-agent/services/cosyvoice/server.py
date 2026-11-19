"""CosyVoice2 本地 TTS HTTP 服务。

只暴露两个接口：
- GET  /health  健康检查
- POST /tts     表单参数 text、speaker，返回 audio/wav

模型在启动时常驻显存，推理串行执行，避免并发把显存打满。
"""

from __future__ import annotations

import io
import logging
import os
import threading
import wave
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import torch
from cosyvoice.cli.cosyvoice import AutoModel
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response

logger = logging.getLogger("cosyvoice")
logging.basicConfig(level=logging.INFO)

MODEL_DIR = os.getenv("COSYVOICE_MODEL_DIR", "/models/CosyVoice2-0.5B")
FP16 = os.getenv("COSYVOICE_FP16", "0").lower() in {"1", "true", "yes"}
MAX_CHARS = int(os.getenv("COSYVOICE_MAX_CHARS", "500"))

_model: Any = None
_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _model
    logger.info("加载 CosyVoice2 模型：%s（fp16=%s）", MODEL_DIR, FP16)
    _model = AutoModel(model_dir=MODEL_DIR, fp16=FP16)
    logger.info("模型加载完成，采样率 %s", _model.sample_rate)
    yield
    _model = None


app = FastAPI(title="CosyVoice2 TTS", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if _model is not None else "loading",
        "sample_rate": getattr(_model, "sample_rate", None),
    }


@app.post("/tts")
def tts(
    text: str = Form(...),
    speaker: str = Form("中文女"),
) -> Response:
    content = text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="text 不能为空")
    if len(content) > MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"text 超过 {MAX_CHARS} 字")
    if _model is None:
        raise HTTPException(status_code=503, detail="模型尚未加载完成")

    try:
        with _lock:
            chunks = list(_model.inference_sft(content, speaker, stream=False))
    except Exception as exc:  # noqa: BLE001 - 模型异常原样返回给本地调用方
        logger.exception("语音合成失败")
        raise HTTPException(status_code=500, detail=f"语音合成失败: {exc}") from exc

    if not chunks:
        raise HTTPException(status_code=500, detail="语音合成结果为空")

    speech = torch.cat([item["tts_speech"] for item in chunks], dim=1)
    audio = speech.squeeze(0).float().clamp(-1.0, 1.0).cpu().numpy()
    pcm = (audio * 32767).astype(np.int16).tobytes()

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(_model.sample_rate))
        wav.writeframes(pcm)

    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={"X-Sample-Rate": str(_model.sample_rate)},
    )
