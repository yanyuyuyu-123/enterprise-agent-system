from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductionRecord(Base):
    """每日生产记录：一个班组、一个产品、一天一条。"""

    __tablename__ = "production_records"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    record_no: Mapped[str] = mapped_column(sa.String(24))
    record_date: Mapped[date] = mapped_column(sa.Date)
    team: Mapped[str] = mapped_column(sa.String(32))
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    total_cost: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    wash_yield: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    status: Mapped[str] = mapped_column(
        sa.String(16), default="approved", server_default="approved"
    )
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
