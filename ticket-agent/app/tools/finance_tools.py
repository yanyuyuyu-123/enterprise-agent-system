"""财务工具：汇总指标、账龄、现金流查询与收付款登记。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.schemas.business import CashFlowCreate
from app.services import finance_service, metric_service
from app.services.permission_service import Principal, require_permission

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _ok(data: Any, message: str = "ok", source: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "source": source or {"type": "finance"},
        "message": message,
    }


def _as_date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def tool_metric_query(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    require_permission(principal, "finance_record", "read")
    end = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    start = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end = end or datetime.now(SHANGHAI).date()
    start = start or end.replace(day=1)
    data = metric_service.finance_summary(db, start, end)
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "finance_summary"},
        "message": "ok",
    }


def tool_receivable_payable_aging(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = finance_service.receivable_payable_aging(
        db,
        principal,
        record_type=args.get("record_type"),
        as_of=_as_date(args.get("as_of")),
    )
    return _ok(data)


def tool_cash_flow_list(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = finance_service.list_cash_flows(
        db,
        principal,
        direction=args.get("direction"),
        status=args.get("status"),
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 20),
    )
    return _ok(data)


def tool_create_cash_flow(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    payload = CashFlowCreate(
        direction=args["direction"],
        amount=args["amount"],
        flow_date=_as_date(args.get("flow_date")),
        payment_method=args.get("payment_method"),
        related_order_type=args.get("related_order_type"),
        related_order_id=args.get("related_order_id"),
        remark=args.get("remark"),
    )
    data = finance_service.create_cash_flow(db, principal, payload)
    return _ok(data, "资金流水已登记")
