from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkOrderCategory(Base):
    __tablename__ = "work_order_categories"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(32))
    sort_no: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    device_no: Mapped[str] = mapped_column(sa.String(64))
    device_name: Mapped[str] = mapped_column(sa.String(128))
    model: Mapped[str | None] = mapped_column(sa.String(64))
    location: Mapped[str | None] = mapped_column(sa.String(128))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    status: Mapped[str] = mapped_column(sa.String(16), default="running", server_default="running")
    purchase_date: Mapped[date | None] = mapped_column(sa.Date)
    remark: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    order_no: Mapped[str] = mapped_column(sa.String(20))
    category: Mapped[str] = mapped_column(
        sa.String(32), sa.ForeignKey("work_order_categories.code", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(sa.String(128))
    description: Mapped[str | None] = mapped_column(sa.Text)
    priority: Mapped[str] = mapped_column(sa.String(16), default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(
        sa.String(32), default="supplementing", server_default="supplementing"
    )
    source_type: Mapped[str | None] = mapped_column(sa.String(16))
    source_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    source_name: Mapped[str | None] = mapped_column(sa.String(128))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    creator_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT")
    )
    assignee_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_overdue: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    overdue_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    recall_reason: Mapped[str | None] = mapped_column(sa.String(500))
    transfer_to_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    transfer_status: Mapped[str] = mapped_column(
        sa.String(16), default="none", server_default="none"
    )
    version: Mapped[int] = mapped_column(sa.Integer, default=1, server_default="1")
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


class WorkOrderDevice(Base):
    __tablename__ = "work_order_device"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    device_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("devices.id", ondelete="RESTRICT")
    )
    device_no_snapshot: Mapped[str | None] = mapped_column(sa.String(64))
    device_name_snapshot: Mapped[str | None] = mapped_column(sa.String(128))
    fault_description: Mapped[str | None] = mapped_column(sa.Text)
    repair_result: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class WorkOrderExpense(Base):
    __tablename__ = "work_order_expense"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    expense_type: Mapped[str | None] = mapped_column(sa.String(32))
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class WorkOrderPatrol(Base):
    __tablename__ = "work_order_patrol"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    patrol_area: Mapped[str | None] = mapped_column(sa.String(128))
    hazard_description: Mapped[str | None] = mapped_column(sa.Text)
    rectification_result: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class WorkOrderTransport(Base):
    __tablename__ = "work_order_transport"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    trip_no: Mapped[str | None] = mapped_column(sa.String(64))
    exception_type: Mapped[str | None] = mapped_column(sa.String(32))
    handling_result: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class WorkOrderRecord(Base):
    __tablename__ = "work_order_records"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(sa.String(32))
    from_status: Mapped[str | None] = mapped_column(sa.String(32))
    to_status: Mapped[str | None] = mapped_column(sa.String(32))
    operator_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    operator_name: Mapped[str] = mapped_column(sa.String(64))
    operator_position: Mapped[str | None] = mapped_column(sa.String(48))
    content: Mapped[str | None] = mapped_column(sa.Text)
    comment: Mapped[str | None] = mapped_column(sa.String(500))
    is_agent: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    agent_session_id: Mapped[str | None] = mapped_column(sa.String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class WorkOrderApproval(Base):
    __tablename__ = "work_order_approvals"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    review_round: Mapped[int] = mapped_column(sa.Integer, default=1, server_default="1")
    reviewer_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewer_name: Mapped[str] = mapped_column(sa.String(64))
    result: Mapped[str] = mapped_column(sa.String(16))
    comment: Mapped[str | None] = mapped_column(sa.Text)
    is_agent: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class WorkOrderAttachment(Base):
    __tablename__ = "work_order_attachments"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("work_orders.id", ondelete="RESTRICT")
    )
    file_name: Mapped[str] = mapped_column(sa.String(255))
    stored_name: Mapped[str] = mapped_column(sa.String(255))
    file_path: Mapped[str] = mapped_column(sa.String(512))
    file_size: Mapped[int] = mapped_column(sa.BigInteger)
    mime_type: Mapped[str] = mapped_column(sa.String(64))
    file_ext: Mapped[str] = mapped_column(sa.String(16))
    uploaded_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
