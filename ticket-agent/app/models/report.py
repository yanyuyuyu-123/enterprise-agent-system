from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    report_no: Mapped[str] = mapped_column(sa.String(16))
    report_type: Mapped[str] = mapped_column(sa.String(16))
    period_start: Mapped[date] = mapped_column(sa.Date)
    period_end: Mapped[date] = mapped_column(sa.Date)
    compare_start: Mapped[date | None] = mapped_column(sa.Date)
    compare_end: Mapped[date | None] = mapped_column(sa.Date)
    status: Mapped[str] = mapped_column(
        sa.String(16), default="generating", server_default="generating"
    )
    file_path: Mapped[str | None] = mapped_column(sa.String(512))
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    generated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(sa.String(500))
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class ReportViewer(Base):
    __tablename__ = "report_viewers"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    granted_by: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
