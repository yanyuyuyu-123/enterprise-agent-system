"""V2 主数据接口请求体。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PartnerStatus = Literal["active", "inactive"]
PaymentType = Literal["cash", "credit"]


class SupplierCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    contact_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    payment_type: PaymentType = "cash"
    status: PartnerStatus = "active"
    owner_id: int | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    payment_type: PaymentType | None = None
    status: PartnerStatus | None = None


class CustomerCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    contact_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    status: PartnerStatus = "active"
    owner_id: int | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    status: PartnerStatus | None = None


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    spec: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=16)
    category: str | None = Field(default=None, max_length=32)
    purchase_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    sale_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    is_active: bool = True
    owner_id: int | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    spec: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=16)
    category: str | None = Field(default=None, max_length=32)
    purchase_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    is_active: bool | None = None


class OrderItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    order_date: date | None = None
    expected_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1)
    is_mock: bool = False


class PurchaseOrderUpdate(BaseModel):
    version: int = Field(ge=0)
    supplier_id: int | None = None
    order_date: date | None = None
    expected_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] | None = None


class SalesOrderCreate(BaseModel):
    customer_id: int
    order_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1)
    is_mock: bool = False


class SalesOrderUpdate(BaseModel):
    version: int = Field(ge=0)
    customer_id: int | None = None
    order_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] | None = None


class OrderSubmit(BaseModel):
    version: int = Field(ge=0)


class OrderReview(BaseModel):
    version: int = Field(ge=0)
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)


class OrderVoid(BaseModel):
    version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class MovementItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class StockMovementCreate(BaseModel):
    movement_type: Literal["inbound", "outbound", "purchase_return", "sales_return"]
    warehouse_id: int
    source_type: Literal["purchase_order", "sales_order", "manual"] = "manual"
    source_id: int | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[MovementItemIn] = Field(min_length=1)
    is_mock: bool = False


class MovementExecute(BaseModel):
    version: int = Field(ge=0)
    items: list[MovementItemIn] = Field(min_length=1)


class MovementReverse(BaseModel):
    version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=200)


class CheckItemIn(BaseModel):
    product_id: int
    actual_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class StockCheckCreate(BaseModel):
    warehouse_id: int
    check_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)
    items: list[CheckItemIn] = Field(min_length=1)
    is_mock: bool = False


RecordType = Literal["income", "cost", "expense", "receivable", "payable"]
CounterpartyType = Literal["customer", "supplier", "none"]


class FinanceRecordCreate(BaseModel):
    record_type: RecordType
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    record_date: date | None = None
    counterparty_type: CounterpartyType = "none"
    counterparty_id: int | None = None
    account_subject: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=500)
    is_mock: bool = False


class CashFlowCreate(BaseModel):
    direction: Literal["in", "out"]
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    flow_date: date | None = None
    payment_method: str | None = Field(default=None, max_length=32)
    related_order_type: Literal["purchase_order", "sales_order"] | None = None
    related_order_id: int | None = None
    remark: str | None = Field(default=None, max_length=500)
    is_mock: bool = False
