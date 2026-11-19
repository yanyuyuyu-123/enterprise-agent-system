"""CRM/WMS 工具：客户供应商档案、库存预警处理、盘点单查询。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.alert import Alert
from app.models.business import FinanceRecord
from app.services import alert_service, inventory_service, partner_service
from app.services.permission_service import Principal, require_permission


def _ok(data: Any, message: str = "ok", source: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "source": source or {"type": "business"},
        "message": message,
    }


def _amount(value: Any) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _balance(
    db: Session, *, counterparty_type: str, counterparty_id: int, record_type: str
) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(FinanceRecord.amount), 0)).where(
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.record_type == record_type,
            FinanceRecord.counterparty_type == counterparty_type,
            FinanceRecord.counterparty_id == counterparty_id,
        )
    )
    return Decimal(total or 0)


def _pick(items: list[dict[str, Any]], keyword: str, label: str) -> dict[str, Any]:
    exact = [
        item for item in items if item.get("name") == keyword or item.get("code") == keyword
    ]
    if exact:
        return exact[0]
    if len(items) == 1:
        return items[0]
    names = "、".join(f"{item['code']} {item['name']}" for item in items)
    raise AppError(3000, f"{label}“{keyword}”匹配到 {len(items)} 个（{names}），请写得更具体", 409)


def tool_customer_profile(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "customer", "read")
    if args.get("customer_id"):
        customer = partner_service.get_customer(db, principal, int(args["customer_id"]))
    else:
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            raise AppError(1001, "请提供客户名称或编码", 400)
        data = partner_service.list_customers(
            db, principal, keyword=keyword, page=1, page_size=5
        )
        if not data["items"]:
            raise AppError(3003, "没有找到该客户", 404)
        customer = _pick(data["items"], keyword, "客户")

    receivable = _balance(
        db,
        counterparty_type="customer",
        counterparty_id=customer["id"],
        record_type="receivable",
    )
    credit_limit = Decimal(customer.get("credit_limit") or 0)
    available = credit_limit - receivable
    return _ok(
        {
            **customer,
            "receivable_total": _amount(receivable),
            "credit_available": _amount(available),
            "credit_exceeded": available < 0,
        }
    )


def tool_supplier_profile(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "supplier", "read")
    if args.get("supplier_id"):
        supplier = partner_service.get_supplier(db, principal, int(args["supplier_id"]))
    else:
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            raise AppError(1001, "请提供供应商名称或编码", 400)
        data = partner_service.list_suppliers(
            db, principal, keyword=keyword, page=1, page_size=5
        )
        if not data["items"]:
            raise AppError(3003, "没有找到该供应商", 404)
        supplier = _pick(data["items"], keyword, "供应商")

    payable = _balance(
        db,
        counterparty_type="supplier",
        counterparty_id=supplier["id"],
        record_type="payable",
    )
    return _ok({**supplier, "payable_total": _amount(payable)})


def tool_alert_list(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    data = alert_service.list_alerts(
        db,
        principal,
        status=args.get("status"),
        alert_type=args.get("alert_type"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 20),
    )
    return _ok(data)


def tool_alert_acknowledge(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    alert_id = args.get("alert_id")
    if alert_id is None:
        alert_no = str(args.get("alert_no") or "").strip().upper()
        if not alert_no:
            raise AppError(1001, "请提供预警编号", 400)
        alert_id = db.scalar(select(Alert.id).where(Alert.alert_no == alert_no))
        if alert_id is None:
            raise AppError(3003, "预警不存在", 404)
    data = alert_service.acknowledge(db, principal, int(alert_id))
    return _ok(data, "预警已认领")


def tool_check_list(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    data = inventory_service.list_checks(
        db,
        principal,
        status=args.get("status"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 20),
    )
    return _ok(data)
