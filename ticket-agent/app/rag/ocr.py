"""图片与扫描件 OCR：优先本地 RapidOCR，未安装时回退云 OCR REST。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.rag.parser import TextBlock

LOCAL_ENGINE = "rapidocr-onnxruntime"
CLOUD_ENGINE = "aliyun-ocr"
_TIMEOUT_SECONDS = 30.0

_local_engine: Any = None
_local_missing = False


def _get_local() -> Any:
    global _local_engine, _local_missing
    if _local_engine is not None or _local_missing:
        return _local_engine
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        _local_missing = True
        return None
    _local_engine = RapidOCR()
    return _local_engine


def engine_name() -> str | None:
    if _get_local() is not None:
        return LOCAL_ENGINE
    if settings.aliyun_ocr_endpoint:
        return CLOUD_ENGINE
    return None


def is_configured() -> bool:
    return engine_name() is not None


def _local_blocks(data: bytes) -> list[TextBlock]:
    import cv2
    import numpy as np

    engine = _get_local()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise AppError(4000, "图片无法解析", 422)
    result, _ = engine(image)
    lines = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
    text = "\n".join(line for line in lines if line)
    return [TextBlock(content=text)] if text else []


def _cloud_blocks(data: bytes, file_name: str) -> list[TextBlock]:
    try:
        response = httpx.post(
            settings.aliyun_ocr_endpoint,
            json={
                "image_base64": base64.b64encode(data).decode("ascii"),
                "file_name": file_name,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(4000, "OCR 服务调用失败", 502) from exc

    blocks: list[TextBlock] = []
    for page_no, page in enumerate(body.get("pages") or [], start=1):
        text = str(page.get("text") or "").strip()
        if text:
            blocks.append(TextBlock(content=text, page_no=int(page.get("page_no") or page_no)))
    if not blocks:
        text = str(body.get("text") or "").strip()
        if text:
            blocks.append(TextBlock(content=text, page_no=1))
    return blocks


def _recognize(data: bytes, file_name: str) -> list[TextBlock]:
    if _get_local() is not None:
        return _local_blocks(data)
    if settings.aliyun_ocr_endpoint:
        return _cloud_blocks(data, file_name)
    raise AppError(5002, "OCR 服务未配置", 500)


def ocr_image(path: Path) -> list[TextBlock]:
    """图片 OCR；未识别到文字时给出明确错误。"""
    blocks = _recognize(path.read_bytes(), path.name)
    if not blocks:
        raise AppError(4000, "OCR 未识别到文字", 422)
    return blocks


def ocr_pdf(path: Path) -> list[TextBlock]:
    """扫描版 PDF：逐页提取内嵌图片后再 OCR，保留页码。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[TextBlock] = []
    for page_no, page in enumerate(reader.pages, start=1):
        texts: list[str] = []
        for image in page.images:
            try:
                page_blocks = _recognize(image.data, f"page-{page_no}.png")
            except AppError:
                continue
            texts.extend(block.content for block in page_blocks)
        if texts:
            blocks.append(TextBlock(content="\n".join(texts), page_no=page_no))
    return blocks
