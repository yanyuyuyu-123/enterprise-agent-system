"""工单接口请求体。响应直接返回 service 组织好的字典。"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Priority = Literal["low", "normal", "high", "urgent"]


class DeviceDetailIn(BaseModel):
    device_id: int | None = None
    fault_description: str | None = None


class ExpenseDetailIn(BaseModel):
    expense_type: (
        Literal["travel", "transport", "office", "entertainment", "purchase", "other"] | None
    ) = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)


class PatrolDetailIn(BaseModel):
    patrol_area: str | None = Field(default=None, max_length=128)
    hazard_description: str | None = None


class TransportDetailIn(BaseModel):
    trip_no: str | None = Field(default=None, max_length=64)
    exception_type: str | None = Field(default=None, max_length=32)


class WorkOrderCreate(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=128)
    description: str | None = None
    priority: Priority = "normal"
    device: DeviceDetailIn | None = None
    expense: ExpenseDetailIn | None = None
    patrol: PatrolDetailIn | None = None
    transport: TransportDetailIn | None = None


class VersionedIn(BaseModel):
    version: int = Field(ge=1)


class SupplementIn(VersionedIn):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    priority: Priority | None = None
    device: DeviceDetailIn | None = None
    expense: ExpenseDetailIn | None = None
    patrol: PatrolDetailIn | None = None
    transport: TransportDetailIn | None = None


class AssignIn(VersionedIn):
    assignee_id: int
    comment: str | None = Field(default=None, max_length=500)


class SubmitIn(VersionedIn):
    content: str = Field(min_length=1)
    repair_result: str | None = None
    rectification_result: str | None = None
    handling_result: str | None = None


class ReviewIn(VersionedIn):
    result: Literal["approve", "reject"]
    comment: str | None = None


class RecallIn(VersionedIn):
    reason: str = Field(min_length=1, max_length=500)


class TransferIn(VersionedIn):
    transfer_to_id: int
    comment: str | None = Field(default=None, max_length=500)


class TransferDecisionIn(VersionedIn):
    approve: bool
    comment: str | None = None
