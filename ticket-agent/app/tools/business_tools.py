"""经营数据工具：采购、销售、库存、客户、供应商只读汇总。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import Customer, Supplier
from app.services import metric_service
from app.services.permission_service import Principal, require_permission

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _dates(args: dict[str, Any]) -> tuple[date, date]:
    end = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    start = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end = end or datetime.now(SHANGHAI).date()
    return start or end.replace(day=1), end


def tool_purchase_summary(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "purchase_order", "read")
    start, end = _dates(args)
    data = metric_service.purchase_summary(db, start, end)
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "purchase_summary"},
        "message": "ok",
    }


def tool_sales_summary(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    require_permission(principal, "sales_order", "read")
    start, end = _dates(args)
    data = metric_service.sales_summary(db, start, end)
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "sales_summary"},
        "message": "ok",
    }


def tool_inventory_query(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    require_permission(principal, "inventory", "read")
    start, end = _dates(args)
    warehouse_id = args.get("warehouse_id")
    data = metric_service.inventory_summary(
        db, start, end, int(warehouse_id) if warehouse_id is not None else None
    )
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "inventory_summary"},
        "message": "ok",
    }


def tool_customer_summary(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "customer", "read")
    start, end = _dates(args)
    sales = metric_service.sales_summary(db, start, end)
    total = db.scalar(
        select(func.count()).select_from(Customer).where(Customer.deleted_at.is_(None))
    )
    data = {
        "customer_total": int(total or 0),
        "sales_amount": sales["sales_amount"],
        "top_customers": sales["customers"][:5],
    }
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "customer_summary"},
        "message": "ok",
    }


def tool_supplier_summary(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "supplier", "read")
    total = db.scalar(
        select(func.count()).select_from(Supplier).where(Supplier.deleted_at.is_(None))
    )
    active = db.scalar(
        select(func.count())
        .select_from(Supplier)
        .where(Supplier.deleted_at.is_(None), Supplier.status == "active")
    )
    data = {"supplier_total": int(total or 0), "supplier_active": int(active or 0)}
    return {
        "ok": True,
        "data": data,
        "source": {"type": "metric", "metric": "supplier_summary"},
        "message": "ok",
    }
