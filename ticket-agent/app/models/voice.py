from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VoiceFile(Base):
    """语音文件：录音输入与播报输出共用，7 天后由清理任务删除。"""

    __tablename__ = "voice_files"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    file_name: Mapped[str] = mapped_column(sa.String(255))
    file_path: Mapped[str] = mapped_column(sa.String(512))
    file_ext: Mapped[str] = mapped_column(sa.String(8))
    file_size: Mapped[int] = mapped_column(sa.BigInteger)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    purpose: Mapped[str] = mapped_column(sa.String(16))
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class VoiceTranscript(Base):
    """一次语音转写结果：原始文本、纠错文本、改写文本与确认状态。"""

    __tablename__ = "voice_transcripts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    voice_file_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("voice_files.id", ondelete="CASCADE")
    )
    asr_text: Mapped[str] = mapped_column(sa.Text)
    corrected_text: Mapped[str | None] = mapped_column(sa.Text)
    rewritten_text: Mapped[str | None] = mapped_column(sa.Text)
    final_text: Mapped[str | None] = mapped_column(sa.Text)
    intent: Mapped[str | None] = mapped_column(sa.String(32))
    entities: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    asr_confidence: Mapped[float | None] = mapped_column(sa.Numeric(5, 4))
    semantic_confidence: Mapped[float | None] = mapped_column(sa.Numeric(5, 4))
    suspected_errors: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    needs_confirmation: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    confirmation_question: Mapped[str | None] = mapped_column(sa.String(500))
    confirmed: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Voiceprint(Base):
    """用户声纹：多段录音求平均后的归一化向量，用于唤醒时的本人校验。"""

    __tablename__ = "voiceprints"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    model: Mapped[str] = mapped_column(sa.String(64))
    embedding: Mapped[list[float]] = mapped_column(postgresql.JSONB)
    samples: Mapped[int] = mapped_column(sa.Integer, default=0, server_default=sa.text("0"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
