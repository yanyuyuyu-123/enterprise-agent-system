from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    alert_no: Mapped[str] = mapped_column(sa.String(16))
    alert_type: Mapped[str] = mapped_column(sa.String(32))
    level: Mapped[str] = mapped_column(sa.String(16), default="warning", server_default="warning")
    target_type: Mapped[str] = mapped_column(sa.String(16))
    target_id: Mapped[int] = mapped_column(sa.BigInteger)
    department_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    title: Mapped[str] = mapped_column(sa.String(128))
    content: Mapped[str] = mapped_column(sa.String(1000))
    metric_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 4))
    threshold_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 4))
    period_start: Mapped[date | None] = mapped_column(sa.Date)
    period_end: Mapped[date | None] = mapped_column(sa.Date)
    dedupe_key: Mapped[str] = mapped_column(sa.String(128))
    status: Mapped[str] = mapped_column(sa.String(16), default="open", server_default="open")
    triggered_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    acknowledged_by: Mapped[int | None] = mapped_column(sa.BigInteger)
    acknowledged_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(sa.BigInteger)
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    handle_note: Mapped[str | None] = mapped_column(sa.String(500))
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class SafeStockConfig(Base):
    __tablename__ = "safe_stock_configs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("products.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    safe_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3), default=0, server_default="0")
    updated_by: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
