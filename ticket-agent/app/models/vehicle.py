from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    plate_no: Mapped[str] = mapped_column(sa.String(32))
    model: Mapped[str | None] = mapped_column(sa.String(64))
    vehicle_type: Mapped[str] = mapped_column(
        sa.String(16), default="tractor", server_default="tractor"
    )
    trailer_no: Mapped[str | None] = mapped_column(sa.String(32))
    load_ton: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 1), default=0, server_default="0"
    )
    driver_name: Mapped[str | None] = mapped_column(sa.String(64))
    driver_phone: Mapped[str | None] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(
        sa.String(16), default="available", server_default="available"
    )
    mileage_km: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 1), default=0, server_default="0"
    )
    remark: Mapped[str | None] = mapped_column(sa.String(255))
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


class CarApplication(Base):
    __tablename__ = "car_applications"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    application_no: Mapped[str] = mapped_column(sa.String(32))
    applicant_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    applicant_name: Mapped[str] = mapped_column(sa.String(64))
    department_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("departments.id"))
    start_address: Mapped[str] = mapped_column(sa.String(255))
    end_address: Mapped[str] = mapped_column(sa.String(255))
    start_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    cargo: Mapped[str | None] = mapped_column(sa.String(64))
    tonnage: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 1), default=0, server_default="0"
    )
    project: Mapped[str | None] = mapped_column(sa.String(128))
    reason: Mapped[str | None] = mapped_column(sa.String(255))
    vehicle_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("vehicles.id"))
    plate_no: Mapped[str | None] = mapped_column(sa.String(32))
    driver_name: Mapped[str | None] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(
        sa.String(16), default="pending", server_default="pending"
    )
    mileage_km: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 1), default=0, server_default="0"
    )
    fuel_cost: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 2), default=0, server_default="0"
    )
    toll_fee: Mapped[Decimal] = mapped_column(sa.Numeric(12, 2), default=0, server_default="0")
    parking_fee: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 2), default=0, server_default="0"
    )
    other_fee: Mapped[Decimal] = mapped_column(sa.Numeric(12, 2), default=0, server_default="0")
    total_cost: Mapped[Decimal] = mapped_column(
        sa.Numeric(12, 2), default=0, server_default="0"
    )
    approver_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    approver_name: Mapped[str | None] = mapped_column(sa.String(64))
    approve_comment: Mapped[str | None] = mapped_column(sa.String(255))
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    remark: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
