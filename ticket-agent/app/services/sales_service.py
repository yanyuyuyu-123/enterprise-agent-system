from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import (
    Customer,
    Product,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
    StockMovementItem,
)
from app.models.org import User
from app.schemas.business import (
    OrderItemIn,
    OrderReview,
    OrderSubmit,
    OrderVoid,
    SalesOrderCreate,
    SalesOrderUpdate,
)
from app.services import finance_service
from app.services.doc_no import next_doc_no
from app.services.log_service import write_log_safely
from app.services.mock_service import ensure_mock_writable
from app.services.permission_service import Principal, require_permission
from app.services.scope import department_scope_condition

EDITABLE_STATUS = ("draft", "rejected")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _line_items(
    db: Session, items: list[OrderItemIn]
) -> tuple[list[tuple[Product, Decimal, Decimal, Decimal]], Decimal]:
    product_ids = {item.product_id for item in items}
    products = {
        product.id: product
        for product in db.scalars(
            select(Product).where(
                Product.id.in_(product_ids),
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        ).all()
    }
    if len(products) != len(product_ids):
        raise AppError(3000, "产品不存在或已停用", 409)
    rows: list[tuple[Product, Decimal, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in items:
        amount = (item.quantity * item.unit_price).quantize(Decimal("0.01"))
        rows.append((products[item.product_id], item.quantity, item.unit_price, amount))
        total += amount
    return rows, total.quantize(Decimal("0.01"))


def _load(db: Session, order_id: int) -> SalesOrder:
    row = db.get(SalesOrder, order_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "销售单不存在或不可见", 404)
    return row


def _visible(db: Session, principal: Principal, scope: str, row: SalesOrder) -> None:
    condition = department_scope_condition(
        principal, scope, SalesOrder.department_id, SalesOrder.salesperson_id
    )
    if condition is None:
        return
    if not db.scalar(select(SalesOrder.id).where(SalesOrder.id == row.id, condition)):
        raise AppError(2002, "超出数据范围", 403)


def _payload(db: Session, row: SalesOrder) -> dict[str, Any]:
    items = db.scalars(
        select(SalesOrderItem)
        .where(SalesOrderItem.sales_order_id == row.id)
        .order_by(SalesOrderItem.line_no)
    ).all()
    product_names = {
        product_id: name
        for product_id, name in db.execute(
            select(Product.id, Product.name).where(
                Product.id.in_([item.product_id for item in items])
            )
        ).all()
    }
    customer_name = db.scalar(select(Customer.name).where(Customer.id == row.customer_id))
    salesperson_name = db.scalar(select(User.name).where(User.id == row.salesperson_id))
    executed = {
        product_id: quantity
        for product_id, quantity in db.execute(
            select(StockMovementItem.product_id, func.sum(StockMovementItem.quantity))
            .join(StockMovement, StockMovement.id == StockMovementItem.movement_id)
            .where(
                StockMovement.source_type == "sales_order",
                StockMovement.source_id == row.id,
                StockMovement.status == "approved",
                StockMovement.movement_type == "outbound",
                StockMovement.reversal_of_id.is_(None),
                StockMovement.reversed_at.is_(None),
            )
            .group_by(StockMovementItem.product_id)
        ).all()
    }
    return {
        "id": row.id,
        "order_no": row.order_no,
        "customer_id": row.customer_id,
        "customer_name": customer_name,
        "salesperson_id": row.salesperson_id,
        "salesperson_name": salesperson_name,
        "created_by": row.salesperson_id,
        "department_id": row.department_id,
        "order_date": _iso(row.order_date),
        "status": row.status,
        "fulfillment_status": row.fulfillment_status,
        "total_amount": str(row.total_amount),
        "reviewer_id": row.reviewer_id,
        "reviewed_at": _iso(row.reviewed_at),
        "void_reason": row.void_reason,
        "version": row.version,
        "is_mock": row.is_mock,
        "remark": row.remark,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "items": [
            {
                "id": item.id,
                "line_no": item.line_no,
                "product_id": item.product_id,
                "product_name": product_names.get(item.product_id),
                "quantity": str(item.quantity),
                "executed_quantity": str(executed.get(item.product_id, Decimal("0"))),
                "remaining_quantity": str(
                    max(item.quantity - executed.get(item.product_id, Decimal("0")), Decimal("0"))
                ),
                "unit_price": str(item.unit_price),
                "amount": str(item.amount),
            }
            for item in items
        ],
    }


def list_sales_orders(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    keyword: str | None = None,
    customer_id: int | None = None,
    fulfillment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "read")
    stmt = select(SalesOrder).where(SalesOrder.deleted_at.is_(None))
    condition = department_scope_condition(
        principal, scope, SalesOrder.department_id, SalesOrder.salesperson_id
    )
    if condition is not None:
        stmt = stmt.where(condition)
    if status:
        stmt = stmt.where(SalesOrder.status == status)
    if customer_id is not None:
        stmt = stmt.where(SalesOrder.customer_id == customer_id)
    if fulfillment_status:
        stmt = stmt.where(SalesOrder.fulfillment_status == fulfillment_status)
    if start_date is not None:
        stmt = stmt.where(SalesOrder.order_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(SalesOrder.order_date <= end_date)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(SalesOrder.order_no.ilike(like), SalesOrder.remark.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SalesOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_payload(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_sales_order(db: Session, principal: Principal, order_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "read")
    row = _load(db, order_id)
    _visible(db, principal, scope, row)
    return _payload(db, row)


def create_sales_order(
    db: Session, principal: Principal, payload: SalesOrderCreate
) -> dict[str, Any]:
    require_permission(principal, "sales_order", "create")
    ensure_mock_writable(payload.is_mock)
    customer = db.get(Customer, payload.customer_id)
    if customer is None or customer.deleted_at is not None or customer.status != "active":
        raise AppError(3000, "客户不存在或已停用", 409)
    lines, total = _line_items(db, payload.items)
    row = SalesOrder(
        order_no=next_doc_no(db, "SO", "SO"),
        customer_id=payload.customer_id,
        salesperson_id=principal.user_id,
        department_id=principal.department_id or 0,
        order_date=payload.order_date or _today(),
        status="draft",
        total_amount=total,
        is_mock=payload.is_mock,
        remark=payload.remark,
        version=0,
    )
    db.add(row)
    db.flush()
    for index, (product, quantity, unit_price, amount) in enumerate(lines, start=1):
        db.add(
            SalesOrderItem(
                sales_order_id=row.id,
                line_no=index,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
            )
        )
    write_log_safely(
        db,
        resource="sales_order",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="sales_order",
        target_id=row.order_no,
    )
    db.commit()
    return _payload(db, row)


def update_sales_order(
    db: Session, principal: Principal, order_id: int, payload: SalesOrderUpdate
) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "create")
    row = _load(db, order_id)
    _visible(db, principal, scope, row)
    if row.salesperson_id != principal.user_id:
        raise AppError(2004, "仅制单人可修改", 403)
    if row.status not in EDITABLE_STATUS:
        raise AppError(3001, "当前状态不允许修改", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None or customer.deleted_at is not None or customer.status != "active":
            raise AppError(3000, "客户不存在或已停用", 409)
        row.customer_id = payload.customer_id
    if payload.order_date is not None:
        row.order_date = payload.order_date
    if payload.remark is not None:
        row.remark = payload.remark
    if payload.items is not None:
        lines, total = _line_items(db, payload.items)
        db.execute(delete(SalesOrderItem).where(SalesOrderItem.sales_order_id == row.id))
        for index, (product, quantity, unit_price, amount) in enumerate(lines, start=1):
            db.add(
                SalesOrderItem(
                    sales_order_id=row.id,
                    line_no=index,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=unit_price,
                    amount=amount,
                )
            )
        row.total_amount = total
    row.version += 1
    db.commit()
    return _payload(db, row)


def submit_sales_order(
    db: Session, principal: Principal, order_id: int, payload: OrderSubmit
) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "create")
    row = _load(db, order_id)
    _visible(db, principal, scope, row)
    if row.salesperson_id != principal.user_id:
        raise AppError(2004, "仅制单人可提交", 403)
    if row.status not in EDITABLE_STATUS:
        raise AppError(3001, "当前状态不允许提交", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    row.status = "pending_review"
    row.version += 1
    if principal.has_position("biz_head"):
        # 业务负责人自建单据免审，提交即通过
        row.status = "approved"
        row.reviewer_id = principal.user_id
        row.reviewed_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        finance_service.generate_sales_approval(
            db,
            principal,
            order_id=row.id,
            amount=row.total_amount,
            order_date=row.order_date,
            department_id=row.department_id,
            customer_id=row.customer_id,
        )
    write_log_safely(
        db,
        resource="sales_order",
        action="submit",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="sales_order",
        target_id=row.order_no,
    )
    db.commit()
    return _payload(db, row)


def review_sales_order(
    db: Session, principal: Principal, order_id: int, payload: OrderReview
) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "review")
    row = _load(db, order_id)
    _visible(db, principal, scope, row)
    if row.status != "pending_review":
        raise AppError(3001, "当前状态不允许审核", 409)
    if row.salesperson_id == principal.user_id:
        raise AppError(3000, "制单人与审核人不能是同一人", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    if payload.decision == "reject" and not payload.comment:
        raise AppError(3000, "驳回必须填写意见", 409)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    row.reviewer_id = principal.user_id
    row.reviewed_at = now
    row.version += 1
    if payload.decision == "approve":
        row.status = "approved"
        finance_service.generate_sales_approval(
            db,
            principal,
            order_id=row.id,
            amount=row.total_amount,
            order_date=row.order_date,
            department_id=row.department_id,
            customer_id=row.customer_id,
        )
    else:
        row.status = "rejected"
    write_log_safely(
        db,
        resource="sales_order",
        action="review",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="sales_order",
        target_id=row.order_no,
    )
    db.commit()
    return _payload(db, row)


def void_sales_order(
    db: Session, principal: Principal, order_id: int, payload: OrderVoid
) -> dict[str, Any]:
    scope = require_permission(principal, "sales_order", "review")
    row = _load(db, order_id)
    _visible(db, principal, scope, row)
    if row.status not in ("draft", "pending_review", "approved"):
        raise AppError(3001, "仅草稿、待审核或已通过单据可作废", 409)
    if row.version != payload.version:
        raise AppError(3002, "单据已被他人更新，请刷新后重试", 409)
    related = db.scalar(
        select(StockMovement.movement_no)
        .where(
            StockMovement.source_type == "sales_order",
            StockMovement.source_id == row.id,
            StockMovement.status.in_(("draft", "pending_execute", "pending_review", "approved")),
            StockMovement.reversed_at.is_(None),
            StockMovement.reversal_of_id.is_(None),
            StockMovement.deleted_at.is_(None),
        )
        .limit(1)
    )
    if related is not None:
        raise AppError(
            3009, f"该订单已有有效出入库单（{related}），请先冲销或作废后再作废订单", 409
        )
    row.status = "void"
    row.void_reason = payload.reason
    row.version += 1
    finance_service.void_by_source(db, "sales_order", row.id, payload.reason)
    write_log_safely(
        db,
        resource="sales_order",
        action="void",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="sales_order",
        target_id=row.order_no,
    )
    db.commit()
    return _payload(db, row)
