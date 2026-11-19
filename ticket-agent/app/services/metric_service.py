"""V2 指标口径：一个指标一个函数，接口与 Agent 共用（development_rules 13.8）。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import (
    CashFlow,
    Customer,
    FinanceRecord,
    Inventory,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
    StockMovementItem,
)

MONEY = Decimal("0.01")
QUANTITY = Decimal("0.001")

METRIC_DEFS: dict[str, dict[str, str]] = {
    "purchase_summary": {
        "formula": "采购数量=Σ明细数量；采购金额=Σ明细金额；平均采购价=金额/数量",
        "source": "purchase_orders + purchase_order_items（approved）",
        "period": "order_date",
        "version": "v2",
    },
    "sales_summary": {
        "formula": "销售数量=Σ明细数量；销售金额=Σ明细金额；平均售价=金额/数量",
        "source": "sales_orders + sales_order_items（approved）",
        "period": "order_date",
        "version": "v2",
    },
    "inventory_summary": {
        "formula": "结存=Σinventory.quantity；周转=期间出库/平均结存；损耗=盘点差异",
        "source": "inventory + stock_movements + stock_movement_items",
        "period": "reviewed_at",
        "version": "v2",
    },
    "finance_summary": {
        "formula": "毛利=收入-成本；净利=收入-成本-费用；资金余额=流入-流出",
        "source": "finance_records + cash_flows（approved）",
        "period": "record_date / flow_date",
        "version": "v2",
    },
}


def _money(value: Decimal | None) -> str:
    return str((value or Decimal("0")).quantize(MONEY))


def _quantity(value: Decimal | None) -> str:
    return str((value or Decimal("0")).quantize(QUANTITY))


def _ratio(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return float(round(numerator / denominator * 100, 2))


def _period_filters(column, start_date: date, end_date: date):
    return column >= start_date, column <= end_date


def purchase_summary(db: Session, start_date: date, end_date: date) -> dict[str, Any]:
    stmt = (
        select(
            func.coalesce(func.sum(PurchaseOrderItem.quantity), 0),
            func.coalesce(func.sum(PurchaseOrderItem.amount), 0),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(
            PurchaseOrder.status == "approved",
            PurchaseOrder.deleted_at.is_(None),
            *_period_filters(PurchaseOrder.order_date, start_date, end_date),
        )
    )
    quantity, amount = db.execute(stmt).one()
    average = None if quantity == 0 else _money(Decimal(amount) / Decimal(quantity))
    return {
        "purchase_quantity": _quantity(quantity),
        "purchase_amount": _money(amount),
        "average_purchase_price": average,
        "average_purchase_price_note": None if average else "分母为 0",
    }


def sales_summary(db: Session, start_date: date, end_date: date) -> dict[str, Any]:
    stmt = (
        select(
            func.coalesce(func.sum(SalesOrderItem.quantity), 0),
            func.coalesce(func.sum(SalesOrderItem.amount), 0),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
        .where(
            SalesOrder.status == "approved",
            SalesOrder.deleted_at.is_(None),
            *_period_filters(SalesOrder.order_date, start_date, end_date),
        )
    )
    quantity, amount = db.execute(stmt).one()
    total_amount = Decimal(amount)
    average = None if quantity == 0 else _money(Decimal(amount) / Decimal(quantity))
    per_customer = db.execute(
        select(
            SalesOrder.customer_id,
            Customer.name,
            func.coalesce(func.sum(SalesOrderItem.quantity), 0),
            func.coalesce(func.sum(SalesOrderItem.amount), 0),
        )
        .join(SalesOrderItem, SalesOrderItem.sales_order_id == SalesOrder.id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
        .where(
            SalesOrder.status == "approved",
            SalesOrder.deleted_at.is_(None),
            *_period_filters(SalesOrder.order_date, start_date, end_date),
        )
        .group_by(SalesOrder.customer_id, Customer.name)
        .order_by(func.sum(SalesOrderItem.amount).desc())
    ).all()
    return {
        "sales_quantity": _quantity(quantity),
        "sales_amount": _money(amount),
        "average_sales_price": average,
        "average_sales_price_note": None if average else "分母为 0",
        "customers": [
            {
                "customer_id": row[0],
                "customer_name": row[1],
                "quantity": _quantity(row[2]),
                "amount": _money(row[3]),
                "share": _ratio(Decimal(row[3]), total_amount),
            }
            for row in per_customer
        ],
    }


def _movement_quantity(
    db: Session, movement_types: tuple[str, ...], start_date, end_date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(StockMovementItem.quantity), 0))
        .join(StockMovement, StockMovement.id == StockMovementItem.movement_id)
        .where(
            StockMovement.status == "approved",
            StockMovement.deleted_at.is_(None),
            StockMovement.movement_type.in_(movement_types),
            *_period_filters(StockMovement.reviewed_at, start_date, end_date),
        )
    )
    return Decimal(db.scalar(stmt) or 0)


def inventory_summary(
    db: Session, start_date: date, end_date: date, warehouse_id: int | None = None
) -> dict[str, Any]:
    stock_stmt = select(func.coalesce(func.sum(Inventory.quantity), 0))
    if warehouse_id is not None:
        stock_stmt = stock_stmt.where(Inventory.warehouse_id == warehouse_id)
    closing = Decimal(db.scalar(stock_stmt) or 0)

    inbound = _movement_quantity(db, ("inbound", "stocktake_in"), start_date, end_date)
    outbound = _movement_quantity(db, ("outbound", "stocktake_out", "loss"), start_date, end_date)
    opening = closing - inbound + outbound
    average_stock = (opening + closing) / 2
    turnover = None if average_stock <= 0 else float(round(outbound / average_stock, 2))

    product_rows = db.execute(
        select(
            Product.id,
            Product.name,
            Product.unit,
            Product.purchase_price,
            Product.sale_price,
            func.coalesce(func.sum(Inventory.quantity), 0),
        )
        .join(Inventory, Inventory.product_id == Product.id)
        .where(Product.deleted_at.is_(None))
        .group_by(
            Product.id,
            Product.name,
            Product.unit,
            Product.purchase_price,
            Product.sale_price,
        )
        .order_by(Product.id)
    ).all()
    products = []
    stock_value_cost = Decimal("0")
    stock_value_sale = Decimal("0")
    for row in product_rows:
        quantity = Decimal(row[5] or 0)
        cost_value = quantity * Decimal(row[3] or 0)
        sale_value = quantity * Decimal(row[4] or 0)
        stock_value_cost += cost_value
        stock_value_sale += sale_value
        products.append(
            {
                "product_id": row[0],
                "product_name": row[1],
                "unit": row[2] or "吨",
                "quantity": _quantity(quantity),
                "purchase_price": _money(row[3]),
                "sale_price": _money(row[4]),
                "cost_value": _money(cost_value),
                "sale_value": _money(sale_value),
            }
        )
    return {
        "closing_quantity": _quantity(closing),
        "inbound_quantity": _quantity(inbound),
        "outbound_quantity": _quantity(outbound),
        "opening_quantity": _quantity(opening),
        "average_stock": _quantity(average_stock),
        "stock_value_cost": _money(stock_value_cost),
        "stock_value_sale": _money(stock_value_sale),
        "products": products,
        "turnover": turnover,
        "turnover_note": None if turnover is not None else "分母为 0",
        "natural_loss": _quantity(_movement_quantity(db, ("stocktake_out",), start_date, end_date)),
    }


def finance_trend(db: Session, months: int = 12) -> dict[str, Any]:
    """按自然月汇总收入、成本、费用和净利，返回连续月份序列。"""
    latest = db.scalar(
        select(func.max(FinanceRecord.record_date)).where(
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
        )
    )
    end = (latest or date.today()).replace(day=1)
    start = end
    for _ in range(max(months, 1) - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    next_month = (end + timedelta(days=32)).replace(day=1)

    month_col = func.date_trunc("month", FinanceRecord.record_date)
    rows = db.execute(
        select(
            month_col,
            FinanceRecord.record_type,
            func.coalesce(func.sum(FinanceRecord.amount), 0),
        )
        .where(
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.record_date >= start,
            FinanceRecord.record_date < next_month,
        )
        .group_by(month_col, FinanceRecord.record_type)
    ).all()
    buckets: dict[str, dict[str, Decimal]] = {}
    for month, record_type, amount in rows:
        buckets.setdefault(month.strftime("%Y-%m"), {})[record_type] = Decimal(amount or 0)

    items = []
    cursor = start
    while cursor < next_month:
        bucket = buckets.get(cursor.strftime("%Y-%m"), {})
        income = bucket.get("income", Decimal("0")) - bucket.get(
            "income_reversal", Decimal("0")
        )
        cost = bucket.get("cost", Decimal("0")) - bucket.get("cost_reversal", Decimal("0"))
        expense = bucket.get("expense", Decimal("0"))
        items.append(
            {
                "period": cursor.strftime("%Y-%m"),
                "revenue": _money(income),
                "cost": _money(cost),
                "gross_profit": _money(income - cost),
                "net_profit": _money(income - cost - expense),
            }
        )
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return {
        "items": items,
        "period_start": start.isoformat(),
        "period_end": (next_month - timedelta(days=1)).isoformat(),
    }


def finance_summary(db: Session, start_date: date, end_date: date) -> dict[str, Any]:
    def total(record_type: str, start: date | None = None) -> Decimal:
        stmt = select(func.coalesce(func.sum(FinanceRecord.amount), 0)).where(
            FinanceRecord.status == "approved",
            FinanceRecord.record_type == record_type,
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.record_date <= end_date,
        )
        if start is not None:
            stmt = stmt.where(FinanceRecord.record_date >= start)
        return Decimal(db.scalar(stmt) or 0)

    income = total("income", start_date) - total("income_reversal", start_date)
    cost = total("cost", start_date) - total("cost_reversal", start_date)
    expense = total("expense", start_date)
    receivable = total("receivable", start_date)
    payable = total("payable", start_date)
    gross_profit = income - cost
    net_profit = gross_profit - expense

    def flow_sum(direction: str, start: date | None = None) -> Decimal:
        stmt = select(func.coalesce(func.sum(CashFlow.amount), 0)).where(
            CashFlow.status == "approved",
            CashFlow.direction == direction,
            CashFlow.deleted_at.is_(None),
            CashFlow.flow_date <= end_date,
        )
        if start is not None:
            stmt = stmt.where(CashFlow.flow_date >= start)
        return Decimal(db.scalar(stmt) or 0)

    inflow = flow_sum("in", start_date)
    outflow = flow_sum("out", start_date)
    balance = flow_sum("in") - flow_sum("out")
    return {
        "revenue": _money(income),
        "cost": _money(cost),
        "expense": _money(expense),
        "gross_profit": _money(gross_profit),
        "gross_margin": _ratio(gross_profit, income),
        "gross_margin_note": None if income != 0 else "分母为 0",
        "net_profit": _money(net_profit),
        "receivable": _money(receivable),
        "payable": _money(payable),
        "cash_balance": _money(balance),
        "cash_inflow": _money(inflow),
        "cash_outflow": _money(outflow),
        "net_cash_flow": _money(inflow - outflow),
        "basis": {"profit": "accrual", "cash": "actual"},
    }
