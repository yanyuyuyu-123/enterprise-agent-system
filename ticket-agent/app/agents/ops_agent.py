"""企业运营分析 Agent：采购、销售、库存、客户、供应商的只读汇总。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import Customer, PurchaseOrder, SalesOrder, Supplier
from app.services import metric_service
from app.services.permission_service import Principal, require_permission

SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_SUBTASKS = 3

TITLES = {
    "purchase": "采购汇总",
    "sales": "销售汇总",
    "inventory": "库存汇总",
    "supplier": "供应商汇总",
}

KEYWORDS = {
    "purchase": ("采购", "进货"),
    "sales": ("销售", "客户", "营收", "回款"),
    "inventory": (
        "库存",
        "结存",
        "周转",
        "积压",
        "出入库",
        "出库",
        "入库",
        "台账",
        "流水",
        "存煤",
        "存量",
        "库存金额",
        "煤价",
        "售价",
        "涨价",
        "降价",
        "吨煤",
    ),
    "supplier": ("供应商",),
}

PRICE_PATTERN = re.compile(r"(降|跌|下调|减|涨|升|上调|加)\s*(?:价)?\s*(\d+(?:\.\d+)?)\s*元")

PERMISSIONS = {
    "purchase": ("purchase_order", "read"),
    "sales": ("sales_order", "read"),
    "inventory": ("inventory", "read"),
    "supplier": ("supplier", "read"),
}


def _period(
    db: Session, start_date: date | None, end_date: date | None
) -> tuple[date, date, str]:
    end = end_date or datetime.now(SHANGHAI).date()
    start = start_date or end.replace(day=1)
    if start_date or end_date:
        return start, end, ""
    latest = db.scalar(select(func.max(SalesOrder.order_date)))
    if latest and latest < start:
        return (
            latest.replace(day=1),
            latest,
            f"本月暂无业务数据，已按最近有数据的 {latest:%Y-%m} 统计。",
        )
    return start, end, ""


def _supplier_summary(db: Session) -> dict[str, Any]:
    total = db.scalar(
        select(func.count()).select_from(Supplier).where(Supplier.deleted_at.is_(None))
    )
    active = db.scalar(
        select(func.count())
        .select_from(Supplier)
        .where(Supplier.deleted_at.is_(None), Supplier.status == "active")
    )
    rows = db.execute(
        select(Supplier.code, Supplier.name, Supplier.payment_type)
        .where(Supplier.deleted_at.is_(None))
        .order_by(Supplier.id.desc())
        .limit(5)
    ).all()
    return {
        "supplier_total": int(total or 0),
        "supplier_active": int(active or 0),
        "recent_suppliers": [
            {"code": row[0], "name": row[1], "payment_type": row[2]} for row in rows
        ],
    }


def _customer_summary(db: Session, start: date, end: date) -> dict[str, Any]:
    total = db.scalar(
        select(func.count()).select_from(Customer).where(Customer.deleted_at.is_(None))
    )
    sales = metric_service.sales_summary(db, start, end)
    return {
        "customer_total": int(total or 0),
        "top_customers": sales["customers"][:5],
        "sales_amount": sales["sales_amount"],
    }


def _run_metric(
    db: Session, principal: Principal, name: str, start: date, end: date
) -> dict[str, Any]:
    resource, action = PERMISSIONS[name]
    require_permission(principal, resource, action)
    if name == "purchase":
        return metric_service.purchase_summary(db, start, end)
    if name == "sales":
        return metric_service.sales_summary(db, start, end)
    if name == "inventory":
        return metric_service.inventory_summary(db, start, end)
    if name == "supplier":
        return _supplier_summary(db)
    raise AppError(1000, "未知指标", 400)


def _has_mock(db: Session, start: date, end: date) -> bool:
    for model, column in (
        (PurchaseOrder, PurchaseOrder.order_date),
        (SalesOrder, SalesOrder.order_date),
    ):
        exists = db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.is_mock.is_(True), column >= start, column <= end)
        )
        if exists:
            return True
    return False


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _price_impact(data: dict[str, Any], question: str) -> str | None:
    """按问题里的涨降价幅度，用当前结存数量测算金额变化。"""
    match = PRICE_PATTERN.search(question)
    if not match:
        return None
    word, raw = match.group(1), Decimal(match.group(2))
    down = word in ("降", "跌", "下调", "减")
    products = data.get("products") or []
    targets = [item for item in products if item["product_name"] in question] or products
    if not targets:
        return None
    segments = []
    for item in targets:
        amount = _money(Decimal(item["quantity"]) * raw)
        segments.append(
            f"{item['product_name']}结存 {item['quantity']} {item['unit']}，"
            f"每吨{'降' if down else '涨'} {raw} 元，"
            f"库存金额{'减少' if down else '增加'} {amount} 元"
        )
    return "价格变动测算：" + "；".join(segments)


def _compose(name: str, data: dict[str, Any]) -> str:
    if name == "purchase":
        return (
            f"采购数量 {data['purchase_quantity']}，金额 {data['purchase_amount']} 元，"
            f"平均采购价 {data['average_purchase_price'] or '—'}"
        )
    if name == "sales":
        return (
            f"销售数量 {data['sales_quantity']}，金额 {data['sales_amount']} 元，"
            f"平均售价 {data['average_sales_price'] or '—'}"
        )
    if name == "inventory":
        parts = [
            f"当前结存 {data['closing_quantity']}，期间入库 {data['inbound_quantity']}、"
            f"出库 {data['outbound_quantity']}，周转率 {data['turnover'] or '—'}",
            f"库存金额（成本价）{data['stock_value_cost']} 元，按售价计 "
            f"{data['stock_value_sale']} 元",
        ]
        for item in data.get("products") or []:
            margin = _money(Decimal(item["sale_price"]) - Decimal(item["purchase_price"]))
            parts.append(
                f"{item['product_name']} {item['quantity']} {item['unit']}"
                f"（成本价 {item['purchase_price']} 元/{item['unit']}，"
                f"售价 {item['sale_price']} 元/{item['unit']}，价差 {margin} 元/{item['unit']}）"
            )
        return "；".join(parts)
    return f"供应商合计 {data['supplier_total']} 家，其中启用 {data['supplier_active']} 家"


def run(
    db: Session,
    principal: Principal,
    question: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    start, end, period_note = _period(db, start_date, end_date)
    subtasks = [name for name, words in KEYWORDS.items() if any(w in question for w in words)]
    if not subtasks:
        subtasks = ["sales", "inventory"]
    subtasks = subtasks[:MAX_SUBTASKS]

    sources: list[dict[str, Any]] = []
    missing: list[str] = []
    lines: list[str] = []
    metrics: dict[str, dict[str, Any]] = {}
    for name in subtasks:
        try:
            data = _run_metric(db, principal, name, start, end)
        except AppError as exc:
            missing.append(f"{TITLES[name]}（{exc.message}）")
            continue
        metrics[name] = data
        sources.append(
            {
                "type": "metric",
                "id": name,
                "title": TITLES[name],
                "locator": f"{start.isoformat()}~{end.isoformat()}",
            }
        )
        lines.append(f"{TITLES[name]}：{_compose(name, data)}")

    if not lines:
        status = "failed"
    elif missing:
        status = "partial"
    else:
        status = "ok"
    if "inventory" in metrics:
        impact = _price_impact(metrics["inventory"], question)
        if impact:
            lines.append(impact)
    prefix = "【模拟数据】" if _has_mock(db, start, end) else ""
    if period_note:
        lines.insert(0, period_note)
    if missing:
        lines.append(f"缺失：{'；'.join(missing)}")
    return {
        "status": status,
        "answer": prefix + "\n".join(lines),
        "sources": sources,
        "missing": missing,
    }
