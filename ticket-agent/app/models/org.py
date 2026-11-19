from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(64))
    parent_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("departments.id"))
    sort_no: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(48))
    name: Mapped[str] = mapped_column(sa.String(48))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    data_scope: Mapped[str] = mapped_column(sa.String(24))
    business_domain: Mapped[str | None] = mapped_column(sa.String(24))
    description: Mapped[str | None] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    employee_no: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(64))
    phone: Mapped[str | None] = mapped_column(sa.String(20))
    email: Mapped[str | None] = mapped_column(sa.String(128))
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    status: Mapped[str] = mapped_column(sa.String(16), default="active", server_default="active")
    is_system: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    # 直接上级，用于 self_and_subordinates 数据范围；为空表示无上级
    manager_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    hired_at: Mapped[date | None] = mapped_column(sa.Date)
    left_at: Mapped[date | None] = mapped_column(sa.Date)
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class UserPosition(Base):
    __tablename__ = "user_positions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    position_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("positions.id", ondelete="RESTRICT")
    )
    is_primary: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class PositionPermission(Base):
    __tablename__ = "position_permissions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    position_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("positions.id", ondelete="RESTRICT")
    )
    resource: Mapped[str] = mapped_column(sa.String(32))
    action: Mapped[str] = mapped_column(sa.String(16))
    data_scope: Mapped[str] = mapped_column(sa.String(24))
    business_domain: Mapped[str | None] = mapped_column(sa.String(24))
    is_allowed: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
