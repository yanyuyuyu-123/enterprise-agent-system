from __future__ import annotations

from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(sa.String(32))
    title: Mapped[str] = mapped_column(sa.String(128))
    content: Mapped[str] = mapped_column(sa.String(1000))
    related_type: Mapped[str | None] = mapped_column(sa.String(32))
    related_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    is_read: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    config_key: Mapped[str] = mapped_column(sa.String(128))
    config_value: Mapped[Any] = mapped_column(postgresql.JSONB)
    value_type: Mapped[str] = mapped_column(sa.String(16))
    category: Mapped[str] = mapped_column(sa.String(32))
    description: Mapped[str | None] = mapped_column(sa.String(255))
    is_editable: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    updated_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    log_type: Mapped[str] = mapped_column(
        sa.String(16), default="operation", server_default="operation"
    )
    log_level: Mapped[str] = mapped_column(sa.String(16), default="normal", server_default="normal")
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    user_name_snapshot: Mapped[str | None] = mapped_column(sa.String(64))
    department_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    resource: Mapped[str] = mapped_column(sa.String(32))
    action: Mapped[str] = mapped_column(sa.String(32))
    target_type: Mapped[str | None] = mapped_column(sa.String(32))
    target_id: Mapped[str | None] = mapped_column(sa.String(64))
    result: Mapped[str] = mapped_column(sa.String(16), default="success", server_default="success")
    request_id: Mapped[str | None] = mapped_column(sa.String(64))
    ip: Mapped[str | None] = mapped_column(postgresql.INET)
    detail: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    sensitive_detail: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(sa.String(64))
    user_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    agent_name: Mapped[str] = mapped_column(sa.String(64))
    intent: Mapped[str | None] = mapped_column(sa.String(64))
    tool_name: Mapped[str] = mapped_column(sa.String(64))
    input_summary: Mapped[str | None] = mapped_column(sa.String(500))
    output_summary: Mapped[str | None] = mapped_column(sa.String(500))
    success: Mapped[bool] = mapped_column(sa.Boolean)
    error_code: Mapped[str | None] = mapped_column(sa.String(32))
    latency_ms: Mapped[int] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(sa.String(64))
    user_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(sa.String(16))
    content: Mapped[str] = mapped_column(sa.Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    intent: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class OrderNoSequence(Base):
    __tablename__ = "order_no_sequences"

    seq_type: Mapped[str] = mapped_column(sa.String(8), primary_key=True)
    seq_date: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    current_seq: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class AccountChangeRequest(Base):
    __tablename__ = "account_change_requests"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    request_no: Mapped[str] = mapped_column(sa.String(24))
    request_type: Mapped[str] = mapped_column(sa.String(16))
    target_user_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(sa.String(16), default="pending", server_default="pending")
    requested_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
