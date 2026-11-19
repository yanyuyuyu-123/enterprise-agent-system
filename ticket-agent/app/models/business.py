from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(64))
    address: Mapped[str | None] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
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


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(128))
    contact_name: Mapped[str | None] = mapped_column(sa.String(64))
    phone: Mapped[str | None] = mapped_column(sa.String(20))
    address: Mapped[str | None] = mapped_column(sa.String(255))
    credit_limit: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    status: Mapped[str] = mapped_column(sa.String(16), default="active", server_default="active")
    owner_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
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


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(128))
    contact_name: Mapped[str | None] = mapped_column(sa.String(64))
    phone: Mapped[str | None] = mapped_column(sa.String(20))
    address: Mapped[str | None] = mapped_column(sa.String(255))
    payment_type: Mapped[str] = mapped_column(sa.String(16), default="cash", server_default="cash")
    status: Mapped[str] = mapped_column(sa.String(16), default="active", server_default="active")
    owner_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
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


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32))
    name: Mapped[str] = mapped_column(sa.String(128))
    spec: Mapped[str | None] = mapped_column(sa.String(128))
    unit: Mapped[str | None] = mapped_column(sa.String(16))
    category: Mapped[str | None] = mapped_column(sa.String(32))
    purchase_price: Mapped[Decimal] = mapped_column(
        sa.Numeric(14, 2), default=0, server_default="0"
    )
    sale_price: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.text("true")
    )
    owner_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
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


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    order_no: Mapped[str] = mapped_column(sa.String(20))
    supplier_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("suppliers.id"))
    purchaser_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    department_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("departments.id"))
    order_date: Mapped[date] = mapped_column(sa.Date)
    expected_date: Mapped[date | None] = mapped_column(sa.Date)
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    fulfillment_status: Mapped[str] = mapped_column(
        sa.String(16), default="none", server_default="none"
    )
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("purchase_orders.id")
    )
    line_no: Mapped[int] = mapped_column(sa.Integer)
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    order_no: Mapped[str] = mapped_column(sa.String(20))
    customer_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("customers.id"))
    salesperson_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    department_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("departments.id"))
    order_date: Mapped[date] = mapped_column(sa.Date)
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    fulfillment_status: Mapped[str] = mapped_column(
        sa.String(16), default="none", server_default="none"
    )
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), default=0, server_default="0")
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("sales_orders.id"))
    line_no: Mapped[int] = mapped_column(sa.Integer)
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("warehouses.id"))
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    movement_no: Mapped[str] = mapped_column(sa.String(24))
    movement_type: Mapped[str] = mapped_column(sa.String(16))
    warehouse_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("warehouses.id"))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    source_type: Mapped[str] = mapped_column(sa.String(16))
    source_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    executor_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    executed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    reversal_of_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("stock_movements.id")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class StockMovementItem(Base):
    __tablename__ = "stock_movement_items"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    movement_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("stock_movements.id"))
    line_no: Mapped[int] = mapped_column(sa.Integer)
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    before_quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 3))
    after_quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 3))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class StockCheck(Base):
    __tablename__ = "stock_checks"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    check_no: Mapped[str] = mapped_column(sa.String(24))
    warehouse_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("warehouses.id"))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    check_date: Mapped[date] = mapped_column(sa.Date)
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class StockCheckItem(Base):
    __tablename__ = "stock_check_items"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    check_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("stock_checks.id"))
    product_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("products.id"))
    book_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    actual_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    diff_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 3))
    remark: Mapped[str | None] = mapped_column(sa.String(200))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class FinanceRecord(Base):
    __tablename__ = "finance_records"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    record_no: Mapped[str] = mapped_column(sa.String(24))
    record_type: Mapped[str] = mapped_column(sa.String(16))
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    record_date: Mapped[date] = mapped_column(sa.Date)
    accounting_period: Mapped[str] = mapped_column(sa.String(7))
    counterparty_type: Mapped[str] = mapped_column(
        sa.String(16), default="none", server_default="none"
    )
    counterparty_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    source_type: Mapped[str] = mapped_column(sa.String(16))
    source_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    account_subject: Mapped[str | None] = mapped_column(sa.String(64))
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class CashFlow(Base):
    __tablename__ = "cash_flows"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    flow_no: Mapped[str] = mapped_column(sa.String(24))
    direction: Mapped[str] = mapped_column(sa.String(8))
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    flow_date: Mapped[date] = mapped_column(sa.Date)
    payment_method: Mapped[str | None] = mapped_column(sa.String(32))
    related_order_type: Mapped[str | None] = mapped_column(sa.String(16))
    related_order_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[str] = mapped_column(sa.String(16), default="draft", server_default="draft")
    department_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("departments.id")
    )
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(sa.String(500))
    version: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
    is_mock: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.text("false")
    )
    remark: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
