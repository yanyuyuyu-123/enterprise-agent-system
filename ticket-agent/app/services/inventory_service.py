from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import (
    Inventory,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockCheck,
    StockCheckItem,
    StockMovement,
    StockMovementItem,
    Warehouse,
)
from app.schemas.business import (
    MovementExecute,
    MovementReverse,
    OrderReview,
    OrderSubmit,
    StockCheckCreate,
    StockMovementCreate,
)
from app.services import finance_service, notification_service
from app.services.doc_no import next_doc_no
from app.services.log_service import write_log_safely
from app.services.mock_service import ensure_mock_writable
from app.services.permission_service import Principal, require_permission
from app.services.scope import department_scope_condition

EDITABLE_STATUS = ("draft", "rejected")

# 出入库类型与来源单据的合法组合
MOVEMENT_SOURCE_RULE = {
    "inbound": ("purchase_order", "manual"),
    "outbound": ("sales_order", "manual"),
    "purchase_return": ("purchase_order",),
    "sales_return": ("sales_order",),
}
# 冲销红字单使用的反向类型
REVERSAL_MOVEMENT = {
    "inbound": "outbound",
    "outbound": "inbound",
    "purchase_return": "inbound",
    "sales_return": "outbound",
    "loss": "inbound",
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def list_warehouses(db: Session, principal: Principal) -> list[dict[str, Any]]:
    require_permission(principal, "inventory", "read")
    rows = db.scalars(
        select(Warehouse)
        .where(Warehouse.deleted_at.is_(None), Warehouse.is_active.is_(True))
        .order_by(Warehouse.id)
    ).all()
    return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]


def list_inventory(
    db: Session,
    principal: Principal,
    *,
    warehouse_id: int | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    require_permission(principal, "inventory", "read")
    stmt = (
        select(Inventory, Product, Warehouse)
        .join(Product, Product.id == Inventory.product_id)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .where(Product.deleted_at.is_(None))
    )
    if warehouse_id is not None:
        stmt = stmt.where(Inventory.warehouse_id == warehouse_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where((Product.code.ilike(like)) | (Product.name.ilike(like)))
    rows = db.execute(stmt.order_by(Inventory.warehouse_id, Product.code)).all()
    return [
        {
            "warehouse_id": ware.id,
            "warehouse_name": ware.name,
            "product_id": product.id,
            "product_code": product.code,
            "product_name": product.name,
            "unit": product.unit,
            "quantity": str(inventory.quantity),
            "updated_at": _iso(inventory.updated_at),
        }
        for inventory, product, ware in rows
    ]


def _movement_payload(db: Session, row: StockMovement) -> dict[str, Any]:
    items = db.scalars(
        select(StockMovementItem)
        .where(StockMovementItem.movement_id == row.id)
        .order_by(StockMovementItem.line_no)
    ).all()
    names = {
        product_id: name
        for product_id, name in db.execute(
            select(Product.id, Product.name).where(
                Product.id.in_([item.product_id for item in items])
            )
        ).all()
    }
    warehouse_name = db.scalar(select(Warehouse.name).where(Warehouse.id == row.warehouse_id))
    return {
        "id": row.id,
        "movement_no": row.movement_no,
        "movement_type": row.movement_type,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": warehouse_name,
        "department_id": row.department_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "status": row.status,
        "created_by": row.created_by,
        "executor_id": row.executor_id,
        "executed_at": _iso(row.executed_at),
        "reviewer_id": row.reviewer_id,
        "reviewed_at": _iso(row.reviewed_at),
        "void_reason": row.void_reason,
        "reversal_of_id": row.reversal_of_id,
        "reversed_at": _iso(row.reversed_at),
        "is_reversed": row.reversed_at is not None,
        "version": row.version,
        "is_mock": row.is_mock,
        "remark": row.remark,
        "created_at": _iso(row.created_at),
        "items": [
            {
                "id": item.id,
                "line_no": item.line_no,
                "product_id": item.product_id,
                "product_name": names.get(item.product_id),
                "quantity": str(item.quantity),
                "before_quantity": None
                if item.before_quantity is None
                else str(item.before_quantity),
                "after_quantity": None if item.after_quantity is None else str(item.after_quantity),
            }
            for item in items
        ],
    }


def _load_movement(db: Session, movement_id: int) -> StockMovement:
    row = db.get(StockMovement, movement_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "出入库单不存在或不可见", 404)
    return row


def _visible_movement(db: Session, principal: Principal, scope: str, row: StockMovement) -> None:
    condition = department_scope_condition(
        principal, scope, StockMovement.department_id, StockMovement.created_by
    )
    if condition is None:
        return
    if not db.scalar(select(StockMovement.id).where(StockMovement.id == row.id, condition)):
        raise AppError(2002, "超出数据范围", 403)


def list_movements(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    warehouse_id: int | None = None,
    keyword: str | None = None,
    movement_type: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "read")
    stmt = select(StockMovement).where(StockMovement.deleted_at.is_(None))
    condition = department_scope_condition(
        principal, scope, StockMovement.department_id, StockMovement.created_by
    )
    if condition is not None:
        stmt = stmt.where(condition)
    if status:
        stmt = stmt.where(StockMovement.status == status)
    if warehouse_id is not None:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    if keyword:
        stmt = stmt.where(StockMovement.movement_no.ilike(f"%{keyword.strip()}%"))
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    if source_type:
        stmt = stmt.where(StockMovement.source_type == source_type)
    if source_id is not None:
        stmt = stmt.where(StockMovement.source_id == source_id)
    if start_date is not None:
        stmt = stmt.where(func.date(StockMovement.created_at) >= start_date)
    if end_date is not None:
        stmt = stmt.where(func.date(StockMovement.created_at) <= end_date)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(StockMovement.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_movement_payload(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_movement(db: Session, principal: Principal, movement_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "read")
    row = _load_movement(db, movement_id)
    _visible_movement(db, principal, scope, row)
    return _movement_payload(db, row)


def _validate_products(db: Session, product_ids: set[int]) -> None:
    count = db.scalar(
        select(func.count(Product.id)).where(
            Product.id.in_(product_ids),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
    )
    if count != len(product_ids):
        raise AppError(3000, "产品不存在或已停用", 409)


def _movement_sign(movement_type: str) -> int:
    """入库类为正，出库类为负。"""
    return 1 if movement_type in ("inbound", "sales_return", "stocktake_in") else -1


def _validate_source(
    db: Session, source_type: str, source_id: int | None, *, lock: bool = False
) -> tuple[int | None, int | None]:
    """返回 (供应商ID, 来源单据ID)。lock=True 时对来源单加行锁，防止并发超收。"""
    if source_type == "manual":
        return None, None
    if source_id is None:
        raise AppError(1001, "缺少来源单据", 400)
    if source_type == "purchase_order":
        if lock:
            order = db.scalar(
                select(PurchaseOrder).where(PurchaseOrder.id == source_id).with_for_update()
            )
        else:
            order = db.get(PurchaseOrder, source_id)
        if order is None or order.deleted_at is not None or order.status != "approved":
            raise AppError(3000, "来源采购单不存在或未审核通过", 409)
        return order.supplier_id, order.id
    if lock:
        order = db.scalar(
            select(SalesOrder).where(SalesOrder.id == source_id).with_for_update()
        )
    else:
        order = db.get(SalesOrder, source_id)
    if order is None or order.deleted_at is not None or order.status != "approved":
        raise AppError(3000, "来源销售单不存在或未审核通过", 409)
    return None, order.id


def _order_items(
    db: Session, source_type: str, source_id: int | None
) -> dict[int, tuple[Decimal, Decimal]]:
    """返回来源单据的 产品 -> (订单数量, 单价)。"""
    if source_id is None:
        return {}
    if source_type == "purchase_order":
        rows = db.execute(
            select(
                PurchaseOrderItem.product_id,
                PurchaseOrderItem.quantity,
                PurchaseOrderItem.unit_price,
            ).where(PurchaseOrderItem.purchase_order_id == source_id)
        ).all()
    elif source_type == "sales_order":
        rows = db.execute(
            select(
                SalesOrderItem.product_id,
                SalesOrderItem.quantity,
                SalesOrderItem.unit_price,
            ).where(SalesOrderItem.sales_order_id == source_id)
        ).all()
    else:
        return {}
    result: dict[int, tuple[Decimal, Decimal]] = {}
    for product_id, quantity, unit_price in rows:
        current, price = result.get(product_id, (Decimal("0"), unit_price))
        result[product_id] = (current + quantity, price)
    return result


def _movement_sum(
    db: Session, source_type: str, source_id: int | None, movement_types: tuple[str, ...]
) -> dict[int, Decimal]:
    """汇总已审核且未冲销的出入库数量（按产品）。"""
    if source_id is None:
        return {}
    rows = db.execute(
        select(StockMovementItem.product_id, func.sum(StockMovementItem.quantity))
        .join(StockMovement, StockMovement.id == StockMovementItem.movement_id)
        .where(
            StockMovement.source_type == source_type,
            StockMovement.source_id == source_id,
            StockMovement.status == "approved",
            StockMovement.movement_type.in_(movement_types),
            StockMovement.reversal_of_id.is_(None),
            StockMovement.reversed_at.is_(None),
            StockMovement.deleted_at.is_(None),
        )
        .group_by(StockMovementItem.product_id)
    ).all()
    return {product_id: Decimal(quantity or 0) for product_id, quantity in rows}


def _validate_fulfillment(
    db: Session,
    movement_type: str,
    source_type: str,
    source_id: int | None,
    items,
) -> None:
    """校验本次数量不超过订单剩余可执行/可退货数量。"""
    if source_type not in ("purchase_order", "sales_order"):
        return
    ordered = _order_items(db, source_type, source_id)
    if not ordered:
        return
    execution_type = "inbound" if source_type == "purchase_order" else "outbound"
    executed = _movement_sum(db, source_type, source_id, (execution_type,))
    if movement_type in ("inbound", "outbound"):
        for item in items:
            if item.product_id not in ordered:
                raise AppError(3008, f"产品 {item.product_id} 不在来源单据中", 400)
            remaining = ordered[item.product_id][0] - executed.get(item.product_id, Decimal("0"))
            if item.quantity > remaining:
                raise AppError(
                    3007,
                    f"产品 {item.product_id} 剩余可执行数量为 {remaining}，本次 {item.quantity} 超出",
                    409,
                )
        return
    returned = _movement_sum(db, source_type, source_id, (movement_type,))
    for item in items:
        if item.product_id not in ordered:
            raise AppError(3008, f"产品 {item.product_id} 不在来源单据中", 400)
        available = executed.get(item.product_id, Decimal("0")) - returned.get(
            item.product_id, Decimal("0")
        )
        if item.quantity > available:
            raise AppError(
                3007,
                f"产品 {item.product_id} 可退货数量为 {available}，本次 {item.quantity} 超出",
                409,
            )


def _refresh_fulfillment(db: Session, source_type: str, source_id: int | None) -> None:
    """按已审核出入库数量回写订单履约状态。"""
    if source_type not in ("purchase_order", "sales_order") or source_id is None:
        return
    order = (
        db.get(PurchaseOrder, source_id)
        if source_type == "purchase_order"
        else db.get(SalesOrder, source_id)
    )
    if order is None:
        return
    ordered = _order_items(db, source_type, source_id)
    if not ordered:
        order.fulfillment_status = "none"
        return
    execution_type = "inbound" if source_type == "purchase_order" else "outbound"
    executed = _movement_sum(db, source_type, source_id, (execution_type,))
    if all(executed.get(product_id, Decimal("0")) >= quantity for product_id, (quantity, _) in ordered.items()):
        order.fulfillment_status = "completed"
    elif any(executed.get(product_id, Decimal("0")) > 0 for product_id in ordered):
        order.fulfillment_status = "partial"
    else:
        order.fulfillment_status = "none"


def create_movement(
    db: Session, principal: Principal, payload: StockMovementCreate
) -> dict[str, Any]:
    require_permission(principal, "inventory", "create")
    ensure_mock_writable(payload.is_mock)
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None or warehouse.deleted_at is not None or not warehouse.is_active:
        raise AppError(3000, "仓库不存在或已停用", 409)
    product_ids = {item.product_id for item in payload.items}
    if len(product_ids) != len(payload.items):
        raise AppError(1000, "同一产品不能重复录入", 400)
    _validate_products(db, product_ids)
    expected_sources = MOVEMENT_SOURCE_RULE.get(payload.movement_type)
    if expected_sources is None or payload.source_type not in expected_sources:
        raise AppError(1000, "出入库类型与来源单据不匹配", 400)
    _validate_source(db, payload.source_type, payload.source_id)
    _validate_fulfillment(
        db, payload.movement_type, payload.source_type, payload.source_id, payload.items
    )
    row = StockMovement(
        movement_no=next_doc_no(db, "SM", "SM"),
        movement_type=payload.movement_type,
        warehouse_id=payload.warehouse_id,
        department_id=principal.department_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        status="draft",
        created_by=principal.user_id,
        is_mock=payload.is_mock,
        remark=payload.remark,
        version=0,
    )
    db.add(row)
    db.flush()
    for index, item in enumerate(payload.items, start=1):
        db.add(
            StockMovementItem(
                movement_id=row.id,
                line_no=index,
                product_id=item.product_id,
                quantity=item.quantity,
            )
        )
    write_log_safely(
        db,
        resource="inventory",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="stock_movement",
        target_id=row.movement_no,
    )
    db.commit()
    return _movement_payload(db, row)


def submit_movement(
    db: Session, principal: Principal, movement_id: int, payload: OrderSubmit
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "create")
    row = _load_movement(db, movement_id)
    _visible_movement(db, principal, scope, row)
    if row.status not in EDITABLE_STATUS:
        raise AppError(3001, "当前状态不允许提交", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    row.status = "pending_execute"
    row.version += 1
    if principal.has_position("warehouse_head"):
        # 仓库负责人自建单据免审：提交即执行并通过
        row.executor_id = principal.user_id
        row.executed_at = _now()
        row.status = "approved"
        row.reviewer_id = principal.user_id
        row.reviewed_at = row.executed_at
        _apply_items(db, row, _movement_sign(row.movement_type))
        _post_movement_finance(db, principal, row)
        db.flush()
        _refresh_fulfillment(db, row.source_type, row.source_id)
        write_log_safely(
            db,
            resource="inventory",
            action="review",
            user_id=principal.user_id,
            user_name=principal.name,
            department_id=principal.department_id,
            log_level="important",
            target_type="stock_movement",
            target_id=row.movement_no,
            detail={"auto": True},
        )
    if row.status == "pending_execute":
        notification_service.notify_permission_holders(
            db,
            resource="inventory",
            action="update",
            type="stock_movement",
            title="出入库单待执行",
            content=f"单据 {row.movement_no} 已提交，请填写实际数量并执行。",
            related_id=row.id,
            related_type="stock_movement",
            exclude_user_id=principal.user_id,
            department_id=row.department_id,
        )
    db.commit()
    return _movement_payload(db, row)


def execute_movement(
    db: Session, principal: Principal, movement_id: int, payload: MovementExecute
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "update")
    row = _load_movement(db, movement_id)
    _visible_movement(db, principal, scope, row)
    if row.status != "pending_execute":
        raise AppError(3001, "当前状态不允许执行", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    items = db.scalars(
        select(StockMovementItem)
        .where(StockMovementItem.movement_id == row.id)
        .order_by(StockMovementItem.line_no)
    ).all()
    actual = {item.product_id: item.quantity for item in payload.items}
    if set(actual) != {item.product_id for item in items}:
        raise AppError(1000, "执行明细与单据明细不一致", 400)
    for item in items:
        item.quantity = actual[item.product_id]
    _validate_fulfillment(db, row.movement_type, row.source_type, row.source_id, items)
    row.executor_id = principal.user_id
    row.executed_at = _now()
    row.status = "pending_review"
    row.version += 1
    notification_service.notify_permission_holders(
        db,
        resource="inventory",
        action="review",
        type="stock_movement",
        title="出入库单待审核",
        content=f"单据 {row.movement_no} 已执行，请审核。",
        related_id=row.id,
        related_type="stock_movement",
        exclude_user_id=principal.user_id,
        department_id=row.department_id,
    )
    db.commit()
    return _movement_payload(db, row)


def _apply_items(db: Session, movement: StockMovement, sign: int) -> None:
    items = db.scalars(
        select(StockMovementItem)
        .where(StockMovementItem.movement_id == movement.id)
        .order_by(StockMovementItem.line_no)
    ).all()
    for item in items:
        stock = db.scalar(
            select(Inventory)
            .where(
                Inventory.warehouse_id == movement.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .with_for_update()
        )
        if stock is None:
            stock = Inventory(
                warehouse_id=movement.warehouse_id,
                product_id=item.product_id,
                quantity=Decimal("0"),
            )
            db.add(stock)
            db.flush()
        before = stock.quantity
        after = before + sign * item.quantity
        if after < 0:
            raise AppError(3000, "库存不足，禁止负库存", 409)
        stock.quantity = after
        item.before_quantity = before
        item.after_quantity = after


def _purchase_cost(db: Session, movement: StockMovement) -> Decimal:
    if movement.movement_type not in ("inbound", "purchase_return") or movement.source_type != "purchase_order":
        return Decimal("0")
    prices = {
        product_id: unit_price
        for product_id, unit_price in db.execute(
            select(PurchaseOrderItem.product_id, PurchaseOrderItem.unit_price).where(
                PurchaseOrderItem.purchase_order_id == movement.source_id
            )
        ).all()
    }
    items = db.scalars(
        select(StockMovementItem).where(StockMovementItem.movement_id == movement.id)
    ).all()
    total = Decimal("0")
    for item in items:
        price = prices.get(item.product_id)
        if price is None:
            raise AppError(3000, "入库明细与采购单不一致，无法计算成本", 409)
        total += item.quantity * price
    return total.quantize(Decimal("0.01"))


def _latest_cost_price(db: Session, product_id: int) -> Decimal:
    """取该产品最近一次已审核采购入库单价，缺失时回退产品采购价。"""
    price = db.scalar(
        select(PurchaseOrderItem.unit_price)
        .join(
            StockMovementItem,
            StockMovementItem.product_id == PurchaseOrderItem.product_id,
        )
        .join(StockMovement, StockMovement.id == StockMovementItem.movement_id)
        .where(
            StockMovement.source_type == "purchase_order",
            StockMovement.source_id == PurchaseOrderItem.purchase_order_id,
            StockMovement.movement_type == "inbound",
            StockMovement.status == "approved",
            StockMovement.reversed_at.is_(None),
            PurchaseOrderItem.product_id == product_id,
        )
        .order_by(StockMovement.reviewed_at.desc().nullslast(), StockMovement.id.desc())
        .limit(1)
    )
    if price is None:
        price = db.scalar(select(Product.purchase_price).where(Product.id == product_id))
    return Decimal(price or 0)


def _movement_amounts(db: Session, row: StockMovement) -> tuple[Decimal, Decimal]:
    """按订单单价与最近采购价计算销售金额和成本金额。"""
    prices = _order_items(db, row.source_type, row.source_id)
    items = db.scalars(
        select(StockMovementItem).where(StockMovementItem.movement_id == row.id)
    ).all()
    income = Decimal("0")
    cost = Decimal("0")
    for item in items:
        price = prices.get(item.product_id, (Decimal("0"), Decimal("0")))[1]
        income += item.quantity * price
        cost += item.quantity * _latest_cost_price(db, item.product_id)
    return income.quantize(Decimal("0.01")), cost.quantize(Decimal("0.01"))


def _post_movement_finance(db: Session, principal: Principal, row: StockMovement) -> None:
    """出入库审核通过后的财务处理：采购成本、销售收入与成本、退货红字。"""
    if row.reviewed_at is None:
        return
    if row.source_type == "purchase_order":
        supplier_id, _ = _validate_source(db, row.source_type, row.source_id)
        if row.movement_type == "inbound":
            finance_service.generate_stock_cost(
                db,
                principal,
                movement_id=row.id,
                amount=_purchase_cost(db, row),
                record_date=row.reviewed_at.date(),
                department_id=row.department_id,
                supplier_id=supplier_id,
            )
        elif row.movement_type == "purchase_return":
            finance_service.generate_return_records(
                db,
                principal,
                movement_id=row.id,
                cost_reversal=_purchase_cost(db, row),
                record_date=row.reviewed_at.date(),
                department_id=row.department_id,
                counterparty_type="supplier",
                counterparty_id=supplier_id,
            )
        return
    if row.source_type == "sales_order" and row.movement_type in ("outbound", "sales_return"):
        order = db.get(SalesOrder, row.source_id)
        if order is None:
            return
        income, cost = _movement_amounts(db, row)
        if row.movement_type == "outbound":
            finance_service.generate_sales_shipping(
                db,
                principal,
                movement_id=row.id,
                income=income,
                cost=cost,
                record_date=row.reviewed_at.date(),
                department_id=row.department_id,
                customer_id=order.customer_id,
            )
        else:
            finance_service.generate_return_records(
                db,
                principal,
                movement_id=row.id,
                income_reversal=income,
                cost_reversal=cost,
                record_date=row.reviewed_at.date(),
                department_id=row.department_id,
                counterparty_type="customer",
                counterparty_id=order.customer_id,
            )


def review_movement(
    db: Session, principal: Principal, movement_id: int, payload: OrderReview
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "review")
    row = _load_movement(db, movement_id)
    _visible_movement(db, principal, scope, row)
    if row.status != "pending_review":
        raise AppError(3001, "当前状态不允许审核", 409)
    if row.created_by == principal.user_id:
        raise AppError(3000, "制单人与审核人不能是同一人", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    if payload.decision == "reject" and not payload.comment:
        raise AppError(3000, "驳回必须填写意见", 409)
    row.reviewer_id = principal.user_id
    row.reviewed_at = _now()
    row.version += 1
    if payload.decision == "approve":
        _validate_source(db, row.source_type, row.source_id, lock=True)
        items = db.scalars(
            select(StockMovementItem).where(StockMovementItem.movement_id == row.id)
        ).all()
        _validate_fulfillment(db, row.movement_type, row.source_type, row.source_id, items)
        _apply_items(db, row, _movement_sign(row.movement_type))
        row.status = "approved"
        _post_movement_finance(db, principal, row)
        db.flush()
        _refresh_fulfillment(db, row.source_type, row.source_id)
    else:
        row.status = "rejected"
    write_log_safely(
        db,
        resource="inventory",
        action="review",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="stock_movement",
        target_id=row.movement_no,
    )
    notification_service.notify(
        db,
        user_id=row.created_by,
        type="stock_movement",
        title="出入库单审核通过" if row.status == "approved" else "出入库单已驳回",
        content=f"单据 {row.movement_no} "
        + ("已审核通过，库存已更新。" if row.status == "approved" else "已被驳回，请查看审核意见。"),
        related_id=row.id,
        related_type="stock_movement",
    )
    db.commit()
    return _movement_payload(db, row)


def reverse_movement(
    db: Session, principal: Principal, movement_id: int, payload: MovementReverse
) -> dict[str, Any]:
    """已审核出入库单红字冲销：生成反向单据并回滚库存。"""
    scope = require_permission(principal, "inventory", "review")
    row = _load_movement(db, movement_id)
    _visible_movement(db, principal, scope, row)
    if not payload.reason or not payload.reason.strip():
        raise AppError(1000, "冲销原因必填", 400)
    if row.status != "approved":
        raise AppError(3001, "只有已审核通过的单据可以冲销", 409)
    if row.reversal_of_id is not None:
        raise AppError(3001, "红字单不能再冲销", 409)
    if row.reversed_at is not None:
        raise AppError(3001, "该单据已冲销", 409)
    if row.source_type == "stock_check":
        raise AppError(3001, "盘点调整单请通过再次盘点修正", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    reversal_type = REVERSAL_MOVEMENT.get(row.movement_type)
    if reversal_type is None:
        raise AppError(3001, "该类型单据不支持冲销", 409)
    items = db.scalars(
        select(StockMovementItem)
        .where(StockMovementItem.movement_id == row.id)
        .order_by(StockMovementItem.line_no)
    ).all()
    now = _now()
    reversal = StockMovement(
        movement_no=next_doc_no(db, "SM", "SM"),
        movement_type=reversal_type,
        warehouse_id=row.warehouse_id,
        department_id=row.department_id,
        source_type=row.source_type,
        source_id=row.source_id,
        status="approved",
        created_by=principal.user_id,
        executor_id=principal.user_id,
        executed_at=now,
        reviewer_id=principal.user_id,
        reviewed_at=now,
        reversal_of_id=row.id,
        is_mock=row.is_mock,
        remark=f"冲销 {row.movement_no}：{payload.reason.strip()}",
        version=0,
    )
    db.add(reversal)
    db.flush()
    for item in items:
        db.add(
            StockMovementItem(
                movement_id=reversal.id,
                line_no=item.line_no,
                product_id=item.product_id,
                quantity=item.quantity,
            )
        )
    db.flush()
    _apply_items(db, reversal, _movement_sign(reversal_type))
    row.reversed_at = now
    row.version += 1
    finance_service.void_by_source(db, "stock_movement", row.id, f"冲销：{payload.reason.strip()}")
    db.flush()
    _refresh_fulfillment(db, row.source_type, row.source_id)
    write_log_safely(
        db,
        resource="inventory",
        action="review",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="stock_movement",
        target_id=row.movement_no,
        detail={"reversal_no": reversal.movement_no, "reason": payload.reason.strip()},
    )
    notification_service.notify(
        db,
        user_id=row.created_by,
        type="stock_movement",
        title="出入库单已冲销",
        content=f"单据 {row.movement_no} 已被冲销，红字单 {reversal.movement_no}。",
        related_id=row.id,
        related_type="stock_movement",
    )
    db.commit()
    return {
        "movement": _movement_payload(db, row),
        "reversal_id": reversal.id,
        "reversal_no": reversal.movement_no,
    }


def _check_payload(db: Session, row: StockCheck) -> dict[str, Any]:
    items = db.scalars(
        select(StockCheckItem).where(StockCheckItem.check_id == row.id).order_by(StockCheckItem.id)
    ).all()
    names = {
        product_id: name
        for product_id, name in db.execute(
            select(Product.id, Product.name).where(
                Product.id.in_([item.product_id for item in items])
            )
        ).all()
    }
    return {
        "id": row.id,
        "check_no": row.check_no,
        "warehouse_id": row.warehouse_id,
        "department_id": row.department_id,
        "check_date": _iso(row.check_date),
        "status": row.status,
        "created_by": row.created_by,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": _iso(row.reviewed_at),
        "version": row.version,
        "is_mock": row.is_mock,
        "remark": row.remark,
        "created_at": _iso(row.created_at),
        "items": [
            {
                "product_id": item.product_id,
                "product_name": names.get(item.product_id),
                "book_quantity": str(item.book_quantity),
                "actual_quantity": str(item.actual_quantity),
                "diff_quantity": str(item.diff_quantity),
                "remark": item.remark,
            }
            for item in items
        ],
    }


def _load_check(db: Session, check_id: int) -> StockCheck:
    row = db.get(StockCheck, check_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "盘点单不存在或不可见", 404)
    return row


def create_check(db: Session, principal: Principal, payload: StockCheckCreate) -> dict[str, Any]:
    require_permission(principal, "inventory", "create")
    ensure_mock_writable(payload.is_mock)
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if warehouse is None or warehouse.deleted_at is not None or not warehouse.is_active:
        raise AppError(3000, "仓库不存在或已停用", 409)
    product_ids = {item.product_id for item in payload.items}
    if len(product_ids) != len(payload.items):
        raise AppError(1000, "同一产品不能重复录入", 400)
    _validate_products(db, product_ids)
    row = StockCheck(
        check_no=next_doc_no(db, "SC", "SC"),
        warehouse_id=payload.warehouse_id,
        department_id=principal.department_id,
        check_date=payload.check_date or _today(),
        status="draft",
        created_by=principal.user_id,
        is_mock=payload.is_mock,
        remark=payload.remark,
        version=0,
    )
    db.add(row)
    db.flush()
    for item in payload.items:
        book = db.scalar(
            select(Inventory.quantity).where(
                Inventory.warehouse_id == payload.warehouse_id,
                Inventory.product_id == item.product_id,
            )
        ) or Decimal("0")
        db.add(
            StockCheckItem(
                check_id=row.id,
                product_id=item.product_id,
                book_quantity=book,
                actual_quantity=item.actual_quantity,
                diff_quantity=item.actual_quantity - book,
            )
        )
    db.commit()
    return _check_payload(db, row)


def submit_check(
    db: Session, principal: Principal, check_id: int, payload: OrderSubmit
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "create")
    row = _load_check(db, check_id)
    condition = department_scope_condition(
        principal, scope, StockCheck.department_id, StockCheck.created_by
    )
    if condition is not None and not db.scalar(
        select(StockCheck.id).where(StockCheck.id == row.id, condition)
    ):
        raise AppError(2002, "超出数据范围", 403)
    if row.status not in EDITABLE_STATUS:
        raise AppError(3001, "当前状态不允许提交", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    row.status = "pending_review"
    row.version += 1
    if principal.has_position("warehouse_head"):
        # 仓库负责人自建盘点单免审，提交即通过
        row.status = "approved"
        row.reviewer_id = principal.user_id
        row.reviewed_at = _now()
        _generate_adjustments(db, principal, row)
        write_log_safely(
            db,
            resource="inventory",
            action="review",
            user_id=principal.user_id,
            user_name=principal.name,
            department_id=principal.department_id,
            log_level="important",
            target_type="stock_check",
            target_id=row.check_no,
            detail={"auto": True},
        )
    if row.status == "pending_review":
        notification_service.notify_permission_holders(
            db,
            resource="inventory",
            action="review",
            type="stock_check",
            title="盘点单待审核",
            content=f"盘点单 {row.check_no} 已提交，请审核。",
            related_id=row.id,
            related_type="stock_check",
            exclude_user_id=principal.user_id,
            department_id=row.department_id,
        )
    db.commit()
    return _check_payload(db, row)


def list_checks(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "inventory", "read")
    stmt = select(StockCheck).where(StockCheck.deleted_at.is_(None))
    condition = department_scope_condition(
        principal, scope, StockCheck.department_id, StockCheck.created_by
    )
    if condition is not None:
        stmt = stmt.where(condition)
    if status:
        stmt = stmt.where(StockCheck.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(StockCheck.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_check_payload(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_check(db: Session, principal: Principal, check_id: int) -> dict[str, Any]:
    require_permission(principal, "inventory", "read")
    return _check_payload(db, _load_check(db, check_id))


def review_check(
    db: Session, principal: Principal, check_id: int, payload: OrderReview
) -> dict[str, Any]:
    require_permission(principal, "inventory", "review")
    row = _load_check(db, check_id)
    if row.status != "pending_review":
        raise AppError(3001, "当前状态不允许审核", 409)
    if row.created_by == principal.user_id:
        raise AppError(3000, "制单人与审核人不能是同一人", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    if payload.decision == "reject" and not payload.comment:
        raise AppError(3000, "驳回必须填写意见", 409)
    row.reviewer_id = principal.user_id
    row.reviewed_at = _now()
    row.version += 1
    if payload.decision == "approve":
        row.status = "approved"
        _generate_adjustments(db, principal, row)
    else:
        row.status = "rejected"
    write_log_safely(
        db,
        resource="inventory",
        action="review",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="stock_check",
        target_id=row.check_no,
    )
    notification_service.notify(
        db,
        user_id=row.created_by,
        type="stock_check",
        title="盘点单审核通过" if row.status == "approved" else "盘点单已驳回",
        content=f"盘点单 {row.check_no} "
        + ("已审核通过，库存调整已生成。" if row.status == "approved" else "已被驳回，请查看审核意见。"),
        related_id=row.id,
        related_type="stock_check",
    )
    db.commit()
    return _check_payload(db, row)


def _generate_adjustments(db: Session, principal: Principal, row: StockCheck) -> None:
    items = db.scalars(select(StockCheckItem).where(StockCheckItem.check_id == row.id)).all()
    adjustments: dict[int, Decimal] = {}
    for item in items:
        current = db.scalar(
            select(Inventory.quantity).where(
                Inventory.warehouse_id == row.warehouse_id,
                Inventory.product_id == item.product_id,
            )
        ) or Decimal("0")
        # book_quantity 是创建盘点单时的快照，差异口径以快照为准；
        # 库存调整按“实盘 - 当前库存”计算，保证最终库存等于实盘数。
        item.diff_quantity = item.actual_quantity - item.book_quantity
        adjustments[item.id] = item.actual_quantity - current
    groups = {
        "stocktake_in": [item for item in items if adjustments[item.id] > 0],
        "stocktake_out": [item for item in items if adjustments[item.id] < 0],
    }
    for movement_type, group in groups.items():
        if not group:
            continue
        movement = StockMovement(
            movement_no=next_doc_no(db, "SM", "SM"),
            movement_type=movement_type,
            warehouse_id=row.warehouse_id,
            department_id=row.department_id,
            source_type="stock_check",
            source_id=row.id,
            status="approved",
            created_by=row.created_by,
            executor_id=principal.user_id,
            executed_at=row.reviewed_at,
            reviewer_id=principal.user_id,
            reviewed_at=row.reviewed_at,
            version=1,
            remark=f"盘点调整 {row.check_no}",
        )
        db.add(movement)
        db.flush()
        for index, item in enumerate(group, start=1):
            db.add(
                StockMovementItem(
                    movement_id=movement.id,
                    line_no=index,
                    product_id=item.product_id,
                    quantity=abs(adjustments[item.id]),
                )
            )
        db.flush()
        _apply_items(db, movement, 1 if movement_type == "stocktake_in" else -1)
