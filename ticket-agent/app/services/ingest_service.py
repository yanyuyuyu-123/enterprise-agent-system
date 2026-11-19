"""知识文档解析流水线：解析 → 分块 → 向量化 → 落库（API 进程后台线程调用）。"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.logging import logger
from app.core.storage import get_storage
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeTranscript
from app.rag import embedder
from app.rag.chunker import split_blocks
from app.rag.parser import media_type_of, parse_file
from app.services.setting_service import get_float, get_int


def parse_document(document_id: int, version: int) -> None:
    db = SessionLocal()
    try:
        _parse(db, document_id, version)
    finally:
        db.close()


def _config_float(db: Session, key: str, default: float) -> float:
    return get_float(db, key, default)


def _parse(db: Session, document_id: int, version: int) -> None:
    document = db.get(KnowledgeDocument, document_id)
    if document is None or document.deleted_at is not None:
        return
    if document.version != version:
        return

    document.status = "parsing"
    document.media_type = media_type_of(document.file_ext)
    document.error_message = None
    db.commit()

    try:
        path = get_storage().path(document.file_path)
        min_chars = int(_config_float(db, "knowledge.ocr.min_chars_per_page", 50.0))
        result = parse_file(path, document.file_ext, min_chars)
        if result.status != "ready":
            document.status = result.status
            document.error_message = result.message
            document.chunk_count = 0
            document.parsed_at = datetime.now(UTC)
            db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
            db.commit()
            return

        if result.transcript is not None:
            transcript = result.transcript
            document.duration_ms = transcript.duration_ms
            db.execute(
                delete(KnowledgeTranscript).where(
                    KnowledgeTranscript.document_id == document.id,
                    KnowledgeTranscript.document_version == version,
                )
            )
            db.add(
                KnowledgeTranscript(
                    document_id=document.id,
                    document_version=version,
                    engine=transcript.engine,
                    language="zh",
                    duration_ms=transcript.duration_ms,
                    original_text=transcript.text,
                    segments=transcript.segments,
                    status="success",
                )
            )
        if result.ocr_engine:
            document.ocr_engine = result.ocr_engine

        size = get_int(db, "knowledge.chunk.size", 600)
        overlap = get_int(db, "knowledge.chunk.overlap", 100)
        batch_size = get_int(db, "embedding.batch_size", 16)
        chunks = split_blocks(result.blocks, size, overlap)
        if not chunks:
            raise AppError(3000, "未抽取到文本内容", 422)

        vectors = embedder.embed_texts([chunk.content for chunk in chunks], batch_size)

        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.document_version == version,
            )
        )
        for chunk, vector in zip(chunks, vectors, strict=True):
            db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    document_version=version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=vector,
                    token_count=len(chunk.content),
                    heading=chunk.heading,
                    page_no=chunk.page_no,
                    sheet_name=chunk.sheet_name,
                    row_no=chunk.row_no,
                    paragraph_no=chunk.paragraph_no,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                )
            )
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.document_version != version,
            )
        )
        document.status = "ready"
        document.embedding_model = settings.embedding_model
        document.chunk_count = len(chunks)
        document.error_message = None
        document.parsed_at = datetime.now(UTC)
        db.commit()
        logger.info(
            "knowledge document parsed",
            extra={"document_id": document.id, "version": version, "chunks": len(chunks)},
        )
    except Exception as exc:  # noqa: BLE001 - 解析失败必须落状态，不能中断任务
        db.rollback()
        message = exc.message if isinstance(exc, AppError) else str(exc)
        document.status = "failed"
        document.error_message = (message or "解析失败")[:500]
        document.parsed_at = datetime.now(UTC)
        db.commit()
        logger.warning(
            "knowledge document parse failed",
            extra={"document_id": document_id, "version": version, "error": message},
        )
        raise


def enqueue_parse(document_id: int, version: int) -> None:
    """在 API 进程的后台线程解析，复用已加载的 embedding 模型，不再依赖 worker。"""
    threading.Thread(target=parse_document, args=(document_id, version), daemon=True).start()
