from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

EMBEDDING_DIM = 1024


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    doc_no: Mapped[str] = mapped_column(sa.String(32))
    title: Mapped[str] = mapped_column(sa.String(255))
    category: Mapped[str] = mapped_column(sa.String(32), default="other", server_default="other")
    file_name: Mapped[str] = mapped_column(sa.String(255))
    file_path: Mapped[str] = mapped_column(sa.String(512))
    file_ext: Mapped[str] = mapped_column(sa.String(16))
    media_type: Mapped[str] = mapped_column(
        sa.String(16), default="document", server_default="document"
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    ocr_engine: Mapped[str | None] = mapped_column(sa.String(32))
    file_size: Mapped[int] = mapped_column(sa.BigInteger)
    file_hash: Mapped[str | None] = mapped_column(sa.String(64))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    visibility_scope: Mapped[str] = mapped_column(
        sa.String(24), default="department", server_default="department"
    )
    owner_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(sa.String(16), default="pending", server_default="pending")
    version: Mapped[int] = mapped_column(sa.Integer, default=1, server_default="1")
    embedding_model: Mapped[str | None] = mapped_column(sa.String(64))
    chunk_count: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(sa.String(500))
    parsed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("knowledge_documents.id"))
    document_version: Mapped[int] = mapped_column(sa.Integer)
    chunk_index: Mapped[int] = mapped_column(sa.Integer)
    content: Mapped[str] = mapped_column(sa.Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    token_count: Mapped[int | None] = mapped_column(sa.Integer)
    heading: Mapped[str | None] = mapped_column(sa.String(255))
    page_no: Mapped[int | None] = mapped_column(sa.Integer)
    sheet_name: Mapped[str | None] = mapped_column(sa.String(64))
    row_no: Mapped[int | None] = mapped_column(sa.Integer)
    paragraph_no: Mapped[int | None] = mapped_column(sa.Integer)
    start_ms: Mapped[int | None] = mapped_column(sa.Integer)
    end_ms: Mapped[int | None] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class KnowledgeTranscript(Base):
    """音视频转写结果：segments 为 [{start_ms, end_ms, text}]，用于生成时间戳分块。"""

    __tablename__ = "knowledge_transcripts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    document_version: Mapped[int] = mapped_column(sa.Integer)
    engine: Mapped[str] = mapped_column(sa.String(32))
    language: Mapped[str] = mapped_column(sa.String(16), default="zh", server_default="zh")
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    original_text: Mapped[str] = mapped_column(sa.Text)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(sa.String(16), default="success", server_default="success")
    error_message: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
