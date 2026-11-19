"""异常预警：9 类场景扫描、去重冷却、状态流转与安全库存维护。"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    CATEGORY_DEVICE_REPAIR,
    CATEGORY_REVIEWER_POSITION,
    SCOPE_BUSINESS_DOMAIN,
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
)
from app.core.errors import AppError
from app.models.alert import Alert, SafeStockConfig
from app.models.business import (
    FinanceRecord,
    Inventory,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
    StockMovementItem,
    Warehouse,
)
from app.models.org import Position, User, UserPosition
from app.models.work_order import WorkOrder
from app.services.log_service import write_log_safely
from app.services.notification_service import notify
from app.services.permission_service import Principal, require_permission
from app.services.recipients import user_ids_by_positions
from app.services.setting_service import get_float, get_int

SHANGHAI = ZoneInfo("Asia/Shanghai")
ALERT_STATUSES = ("open", "acknowledged", "closed")
_OUTBOUND_TYPES = ("outbound", "stocktake_out", "loss")


def _dept_of_position(db: Session, position_code: str) -> int | None:
    return db.scalar(
        select(User.department_id)
        .join(UserPosition, UserPosition.user_id == User.id)
        .join(Position, Position.id == UserPosition.position_id)
        .where(
            Position.code == position_code,
            Position.is_active.is_(True),
            Position.deleted_at.is_(None),
            UserPosition.deleted_at.is_(None),
            User.status == "active",
            User.deleted_at.is_(None),
        )
        .limit(1)
    )


def _alert_no(db: Session) -> str:
    prefix = f"AL{datetime.now(SHANGHAI):%Y%m%d}"
    count = db.scalar(select(func.count(Alert.id)).where(Alert.alert_no.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:03d}"


def _in_cooldown(db: Session, dedupe_key: str, cooldown_hours: int) -> bool:
    cutoff = datetime.now(UTC) - timedelta(hours=cooldown_hours)
    return (
        db.scalar(
            select(Alert.id)
            .where(Alert.dedupe_key == dedupe_key, Alert.triggered_at >= cutoff)
            .limit(1)
        )
        is not None
    )


def _emit(
    db: Session,
    *,
    alert_type: str,
    level: str,
    target_type: str,
    target_id: int,
    department_id: int | None,
    title: str,
    content: str,
    metric_value: Decimal | float | None = None,
    threshold_value: Decimal | float | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    recipients: list[int] | None = None,
    is_mock: bool = False,
) -> bool:
    cooldown_hours = get_int(db, "alert.cooldown_hours", 24)
    dedupe_key = f"{alert_type}:{target_type}:{target_id}"
    if _in_cooldown(db, dedupe_key, cooldown_hours):
        return False

    now = datetime.now(UTC)
    alert = Alert(
        alert_no=_alert_no(db),
        alert_type=alert_type,
        level=level,
        target_type=target_type,
        target_id=target_id,
        department_id=department_id,
        title=title[:128],
        content=content[:1000],
        metric_value=None if metric_value is None else Decimal(str(metric_value)),
        threshold_value=None if threshold_value is None else Decimal(str(threshold_value)),
        period_start=period_start,
        period_end=period_end,
        dedupe_key=dedupe_key,
        status="open",
        triggered_at=now,
        is_mock=is_mock,
    )
    db.add(alert)
    db.flush()

    prefix = "严重异常预警" if level == "critical" else "异常预警"
    mock_prefix = "[模拟数据] " if is_mock else ""
    for user_id in sorted(set(recipients or [])):
        notify(
            db,
            user_id=user_id,
            type="alert_triggered",
            title=f"{mock_prefix}{prefix}：{title}",
            content=content,
            related_id=alert.id,
            related_type="alert",
        )
    write_log_safely(
        db,
        log_type="system",
        resource="alert",
        action="trigger",
        user_name="系统",
        log_level="important",
        target_type=target_type,
        target_id=target_id,
        detail={
            "alert_no": alert.alert_no,
            "alert_type": alert_type,
            "level": level,
            "metric_value": str(metric_value),
            "threshold_value": str(threshold_value),
            "is_mock": is_mock,
        },
    )
    return True


def _low_stock(db: Session, department_id: int | None) -> int:
    rows = db.execute(
        select(
            Inventory.product_id,
            Product.name,
            Inventory.quantity,
            SafeStockConfig.safe_quantity,
        )
        .join(Product, Product.id == Inventory.product_id)
        .join(
            SafeStockConfig,
            and_(
                SafeStockConfig.product_id == Inventory.product_id,
                SafeStockConfig.warehouse_id == Inventory.warehouse_id,
            ),
        )
        .where(Inventory.quantity < SafeStockConfig.safe_quantity, Product.deleted_at.is_(None))
    ).all()
    created = 0
    for product_id, name, quantity, safe_quantity in rows:
        created += int(
            _emit(
                db,
                alert_type="low_stock",
                level="warning",
                target_type="product",
                target_id=product_id,
                department_id=department_id,
                title=f"库存低于安全库存：{name}",
                content=f"当前结存 {quantity}，安全库存 {safe_quantity}。",
                metric_value=quantity,
                threshold_value=safe_quantity,
                recipients=user_ids_by_positions(db, "warehouse_head", "business_head"),
            )
        )
    return created


def _overstock(db: Session, department_id: int | None) -> int:
    days = get_int(db, "alert.overstock.no_sales_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(Inventory.product_id, Product.name, func.sum(Inventory.quantity))
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.quantity > 0, Product.deleted_at.is_(None))
        .group_by(Inventory.product_id, Product.name)
    ).all()
    created = 0
    for product_id, name, quantity in rows:
        recent_outbound = db.scalar(
            select(StockMovementItem.id)
            .join(StockMovement, StockMovement.id == StockMovementItem.movement_id)
            .where(
                StockMovementItem.product_id == product_id,
                StockMovement.movement_type.in_(_OUTBOUND_TYPES),
                StockMovement.status == "approved",
                StockMovement.reviewed_at >= cutoff,
            )
            .limit(1)
        )
        if recent_outbound:
            continue
        created += int(
            _emit(
                db,
                alert_type="overstock",
                level="info",
                target_type="product",
                target_id=product_id,
                department_id=department_id,
                title=f"库存长期积压：{name}",
                content=f"结存 {quantity}，最近 {days} 天无出库记录。",
                metric_value=quantity,
                threshold_value=Decimal(days),
                recipients=user_ids_by_positions(db, "warehouse_head", "business_head"),
            )
        )
    return created


def _weighted_prices(
    db: Session,
    *,
    order_model: Any,
    item_model: Any,
    fk_name: str,
    start: date,
    end: date,
) -> dict[int, Decimal]:
    fk = getattr(item_model, fk_name)
    rows = db.execute(
        select(
            item_model.product_id,
            func.coalesce(func.sum(item_model.quantity), 0),
            func.coalesce(func.sum(item_model.amount), 0),
        )
        .join(order_model, order_model.id == fk)
        .where(
            order_model.status == "approved",
            order_model.deleted_at.is_(None),
            order_model.order_date >= start,
            order_model.order_date <= end,
        )
        .group_by(item_model.product_id)
    ).all()
    result: dict[int, Decimal] = {}
    for product_id, quantity, amount in rows:
        if quantity and Decimal(quantity) > 0:
            result[product_id] = Decimal(amount) / Decimal(quantity)
    return result


def _price_change(
    db: Session,
    *,
    change_type: str,
    order_model: Any,
    item_model: Any,
    fk_name: str,
    department_id: int | None,
    rise: bool,
) -> int:
    window = get_int(db, "alert.price.change_window_days", 30)
    ratio_threshold = get_float(db, "alert.price.change_ratio", 0.15)
    today = datetime.now(SHANGHAI).date()
    current_end = today - timedelta(days=1)
    current_start = current_end - timedelta(days=window - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window - 1)

    current = _weighted_prices(
        db,
        order_model=order_model,
        item_model=item_model,
        fk_name=fk_name,
        start=current_start,
        end=current_end,
    )
    previous = _weighted_prices(
        db,
        order_model=order_model,
        item_model=item_model,
        fk_name=fk_name,
        start=previous_start,
        end=previous_end,
    )
    created = 0
    for product_id, current_price in current.items():
        base = previous.get(product_id)
        if base is None or base == 0:
            continue
        change = (current_price - base) / base
        if rise and change < ratio_threshold:
            continue
        if not rise and change > -ratio_threshold:
            continue
        name = db.scalar(select(Product.name).where(Product.id == product_id)) or str(product_id)
        title = f"采购价格异常上涨：{name}" if rise else f"销售价格异常下降：{name}"
        created += int(
            _emit(
                db,
                alert_type=change_type,
                level="warning",
                target_type="product",
                target_id=product_id,
                department_id=department_id,
                title=title,
                content=(
                    f"近 {window} 天加权均价 {current_price:.2f}，前一同期 {base:.2f}，"
                    f"变化 {change:.2%}。"
                ),
                metric_value=round(float(change), 4),
                threshold_value=ratio_threshold,
                period_start=current_start,
                period_end=current_end,
                recipients=user_ids_by_positions(db, "business_head", "buyer"),
            )
        )
    return created


def _receivable_overdue(db: Session, department_id: int | None) -> int:
    days = get_int(db, "alert.receivable.overdue_days", 30)
    cutoff = datetime.now(SHANGHAI).date() - timedelta(days=days)
    rows = db.execute(
        select(FinanceRecord.id, FinanceRecord.amount, FinanceRecord.source_id)
        .join(SalesOrder, SalesOrder.id == FinanceRecord.source_id)
        .where(
            FinanceRecord.record_type == "receivable",
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.amount > 0,
            SalesOrder.deleted_at.is_(None),
            SalesOrder.order_date <= cutoff,
        )
    ).all()
    created = 0
    for record_id, amount, source_id in rows:
        target_id = source_id or record_id
        created += int(
            _emit(
                db,
                alert_type="receivable_overdue",
                level="critical",
                target_type="sales_order",
                target_id=target_id,
                department_id=department_id,
                title="应收超期未收",
                content=f"应收金额 {amount}，销售单开单已超过 {days} 天。",
                metric_value=amount,
                threshold_value=Decimal(days),
                recipients=user_ids_by_positions(db, "finance_head"),
            )
        )
    return created


def _payable_due(db: Session, department_id: int | None) -> int:
    days = get_int(db, "alert.payable.due_days", 30)
    cutoff = datetime.now(SHANGHAI).date() - timedelta(days=days)
    rows = db.execute(
        select(FinanceRecord.id, FinanceRecord.amount, FinanceRecord.source_id)
        .join(PurchaseOrder, PurchaseOrder.id == FinanceRecord.source_id)
        .where(
            FinanceRecord.record_type == "payable",
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.amount > 0,
            PurchaseOrder.deleted_at.is_(None),
            PurchaseOrder.order_date <= cutoff,
        )
    ).all()
    created = 0
    for record_id, amount, source_id in rows:
        target_id = source_id or record_id
        created += int(
            _emit(
                db,
                alert_type="payable_due",
                level="warning",
                target_type="purchase_order",
                target_id=target_id,
                department_id=department_id,
                title="应付到期未付",
                content=f"应付金额 {amount}，采购单开单已超过 {days} 天。",
                metric_value=amount,
                threshold_value=Decimal(days),
                recipients=user_ids_by_positions(db, "finance_head", "buyer"),
            )
        )
    return created


def _device_fault_repeat(db: Session, department_id: int | None) -> int:
    period_days = get_int(db, "alert.device_fault.period_days", 7)
    repeat_count = get_int(db, "alert.device_fault.repeat_count", 3)
    cutoff = datetime.now(UTC) - timedelta(days=period_days)
    rows = db.execute(
        select(WorkOrder.source_id, func.count())
        .where(
            WorkOrder.category == CATEGORY_DEVICE_REPAIR,
            WorkOrder.source_type == "device",
            WorkOrder.source_id.is_not(None),
            WorkOrder.created_at >= cutoff,
            WorkOrder.deleted_at.is_(None),
        )
        .group_by(WorkOrder.source_id)
        .having(func.count() >= repeat_count)
    ).all()
    created = 0
    for device_id, count in rows:
        created += int(
            _emit(
                db,
                alert_type="device_fault_repeat",
                level="warning",
                target_type="device",
                target_id=device_id,
                department_id=department_id,
                title="设备故障重复发生",
                content=f"最近 {period_days} 天该设备报修 {count} 次，达到阈值 {repeat_count} 次。",
                metric_value=count,
                threshold_value=repeat_count,
                recipients=user_ids_by_positions(db, "production_head"),
            )
        )
    return created


def _profit_decline(db: Session) -> int:
    months = get_int(db, "alert.profit.decline_months", 2)
    points = get_float(db, "alert.profit.decline_points", 5.0)
    today = datetime.now(SHANGHAI).date()
    first_of_month = today.replace(day=1)
    margins: list[float] = []
    for offset in range(months, 0, -1):
        index = first_of_month.year * 12 + first_of_month.month - 1 - offset
        year, month = index // 12, index % 12 + 1
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        totals = dict(
            db.execute(
                select(FinanceRecord.record_type, func.sum(FinanceRecord.amount))
                .where(
                    FinanceRecord.status == "approved",
                    FinanceRecord.deleted_at.is_(None),
                    FinanceRecord.record_type.in_(("income", "cost")),
                    FinanceRecord.record_date >= start,
                    FinanceRecord.record_date <= end,
                )
                .group_by(FinanceRecord.record_type)
            ).all()
        )
        income = Decimal(totals.get("income") or 0)
        cost = Decimal(totals.get("cost") or 0)
        if income <= 0:
            return 0
        margins.append(float((income - cost) / income * 100))

    if len(margins) < 2:
        return 0
    decreasing = all(later < earlier for earlier, later in zip(margins, margins[1:], strict=True))
    drop = margins[0] - margins[-1]
    if not decreasing or drop < points:
        return 0
    return int(
        _emit(
            db,
            alert_type="profit_decline",
            level="critical",
            target_type="company",
            target_id=0,
            department_id=None,
            title="毛利率持续下降",
            content=f"最近 {months} 个完整月毛利率逐月下降，累计下降 {drop:.2f} 个百分点。",
            metric_value=round(drop, 2),
            threshold_value=points,
            recipients=user_ids_by_positions(db, "general_manager", "finance_head"),
        )
    )


def create_work_order_alert(
    db: Session, *, order_id: int, category: str, department_id: int | None, assignee_id: int | None
) -> bool:
    """在超时标记同一事务内调用，不单独提交。"""
    reviewer_position = CATEGORY_REVIEWER_POSITION.get(category)
    recipients = user_ids_by_positions(db, reviewer_position) if reviewer_position else []
    if assignee_id:
        recipients.append(assignee_id)
    return _emit(
        db,
        alert_type="work_order_overdue",
        level="warning",
        target_type="work_order",
        target_id=order_id,
        department_id=department_id,
        title="工单已超时",
        content="工单超过期限仍未完成，请尽快处理。",
        recipients=recipients,
    )


def scan(db: Session) -> dict[str, int]:
    """逐场景扫描，单场景失败只记日志，不影响其他场景。"""
    business_dept = _dept_of_position(db, "business_head")
    finance_dept = _dept_of_position(db, "finance_head")
    production_dept = _dept_of_position(db, "production_head")
    scenarios: tuple[tuple[str, Any], ...] = (
        ("low_stock", lambda: _low_stock(db, business_dept)),
        ("overstock", lambda: _overstock(db, business_dept)),
        (
            "purchase_price_up",
            lambda: _price_change(
                db,
                change_type="purchase_price_up",
                order_model=PurchaseOrder,
                item_model=PurchaseOrderItem,
                fk_name="purchase_order_id",
                department_id=business_dept,
                rise=True,
            ),
        ),
        (
            "sales_price_down",
            lambda: _price_change(
                db,
                change_type="sales_price_down",
                order_model=SalesOrder,
                item_model=SalesOrderItem,
                fk_name="sales_order_id",
                department_id=business_dept,
                rise=False,
            ),
        ),
        ("receivable_overdue", lambda: _receivable_overdue(db, finance_dept)),
        ("payable_due", lambda: _payable_due(db, finance_dept)),
        ("device_fault_repeat", lambda: _device_fault_repeat(db, production_dept)),
        ("profit_decline", lambda: _profit_decline(db)),
    )
    result: dict[str, int] = {}
    for name, handler in scenarios:
        try:
            result[name] = handler()
        except Exception as exc:  # noqa: BLE001 - 单场景失败不阻断整轮
            result[name] = 0
            write_log_safely(
                db,
                log_type="system",
                resource="alert",
                action=f"scan_{name}",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500]},
            )
    write_log_safely(
        db,
        log_type="system",
        resource="alert",
        action="scan",
        user_name="系统",
        detail=result,
    )
    db.commit()
    return result


def _payload(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "alert_no": alert.alert_no,
        "alert_type": alert.alert_type,
        "level": alert.level,
        "target_type": alert.target_type,
        "target_id": alert.target_id,
        "department_id": alert.department_id,
        "title": alert.title,
        "content": alert.content,
        "metric_value": None if alert.metric_value is None else str(alert.metric_value),
        "threshold_value": None if alert.threshold_value is None else str(alert.threshold_value),
        "status": alert.status,
        "triggered_at": alert.triggered_at.isoformat(),
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "closed_at": alert.closed_at.isoformat() if alert.closed_at else None,
        "handle_note": alert.handle_note,
        "is_mock": alert.is_mock,
    }


def list_alerts(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    alert_type: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "alert", "read")
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)
    # 前端下拉清空后仍会带 status=，空串等同于不筛选
    status = status or None
    if status is not None and status not in ALERT_STATUSES:
        raise AppError(1003, "预警状态不存在", 400)
    conditions: list[Any] = []
    if status:
        conditions.append(Alert.status == status)
    if alert_type:
        conditions.append(Alert.alert_type == alert_type)
    if start_at:
        conditions.append(Alert.triggered_at >= start_at)
    if end_at:
        conditions.append(Alert.triggered_at <= end_at)

    if scope != SCOPE_COMPANY:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        dept_condition = Alert.department_id == principal.department_id
        if principal.has_position("general_manager", "finance_head"):
            conditions.append(or_(dept_condition, Alert.department_id.is_(None)))
        else:
            conditions.append(dept_condition)

    total = db.scalar(select(func.count(Alert.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Alert)
        .where(*conditions)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _ensure_department(principal: Principal, scope: str, alert: Alert) -> None:
    if scope == SCOPE_COMPANY:
        return
    if alert.department_id is None:
        if not principal.has_position("general_manager"):
            raise AppError(2001, "无该预警处理权限", 403)
        return
    if alert.department_id != principal.department_id:
        raise AppError(2001, "无该预警处理权限", 403)


def acknowledge(db: Session, principal: Principal, alert_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "alert", "update")
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise AppError(3003, "预警不存在", 404)
    _ensure_department(principal, scope, alert)
    if alert.status != "open":
        raise AppError(3001, "只有待处理预警可以认领", 409)
    alert.status = "acknowledged"
    alert.acknowledged_by = principal.user_id
    alert.acknowledged_at = datetime.now(UTC)
    write_log_safely(
        db,
        resource="alert",
        action="acknowledge",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="alert",
        target_id=alert.id,
        detail={"alert_no": alert.alert_no, "alert_type": alert.alert_type},
    )
    db.commit()
    return _payload(alert)


def close_alert(
    db: Session, principal: Principal, alert_id: int, *, handle_note: str
) -> dict[str, Any]:
    scope = require_permission(principal, "alert", "update")
    note = (handle_note or "").strip()
    if not note:
        raise AppError(1001, "关闭预警必须填写处理说明", 400)
    if len(note) > 500:
        raise AppError(1002, "处理说明不能超过 500 字", 400)
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise AppError(3003, "预警不存在", 404)
    _ensure_department(principal, scope, alert)
    if alert.status != "acknowledged":
        raise AppError(3001, "预警需先认领再关闭", 409)
    alert.status = "closed"
    alert.closed_by = principal.user_id
    alert.closed_at = datetime.now(UTC)
    alert.handle_note = note
    write_log_safely(
        db,
        resource="alert",
        action="close",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="alert",
        target_id=alert.id,
        detail={"alert_no": alert.alert_no, "alert_type": alert.alert_type},
    )
    db.commit()
    return _payload(alert)


def list_safe_stock(db: Session, principal: Principal) -> dict[str, Any]:
    scope = require_permission(principal, "safe_stock", "read")
    stmt = (
        select(
            SafeStockConfig.id,
            SafeStockConfig.product_id,
            Product.code,
            Product.name,
            SafeStockConfig.warehouse_id,
            Warehouse.name,
            SafeStockConfig.safe_quantity,
            SafeStockConfig.updated_at,
        )
        .join(Product, Product.id == SafeStockConfig.product_id)
        .join(Warehouse, Warehouse.id == SafeStockConfig.warehouse_id)
        .order_by(SafeStockConfig.id)
    )
    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        stmt = stmt.join(User, User.id == Product.owner_id).where(
            User.department_id == principal.department_id
        )
    elif scope not in (SCOPE_COMPANY, SCOPE_BUSINESS_DOMAIN):
        raise AppError(2002, "超出数据范围", 403)

    rows = db.execute(stmt).all()
    return {
        "items": [
            {
                "id": row.id,
                "product_id": row.product_id,
                "product_code": row.code,
                "product_name": row.name,
                "warehouse_id": row.warehouse_id,
                "warehouse_name": row.warehouse_name,
                "safe_quantity": str(row.safe_quantity),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    }


def update_safe_stock(
    db: Session,
    principal: Principal,
    *,
    product_id: int,
    warehouse_id: int,
    safe_quantity: Decimal,
) -> dict[str, Any]:
    require_permission(principal, "safe_stock", "update")
    if safe_quantity < 0:
        raise AppError(1002, "安全库存不能为负数", 400)
    product = db.get(Product, product_id)
    warehouse = db.get(Warehouse, warehouse_id)
    if product is None or product.deleted_at is not None:
        raise AppError(3003, "产品不存在", 404)
    if warehouse is None or not warehouse.is_active:
        raise AppError(3003, "仓库不存在", 404)

    config = db.scalar(
        select(SafeStockConfig).where(
            SafeStockConfig.product_id == product_id,
            SafeStockConfig.warehouse_id == warehouse_id,
        )
    )
    if config is None:
        config = SafeStockConfig(
            product_id=product_id,
            warehouse_id=warehouse_id,
            safe_quantity=safe_quantity,
            updated_by=principal.user_id,
        )
        db.add(config)
    else:
        config.safe_quantity = safe_quantity
        config.updated_by = principal.user_id
    write_log_safely(
        db,
        resource="safe_stock",
        action="update",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="product",
        target_id=product_id,
        detail={"warehouse_id": warehouse_id, "safe_quantity": str(safe_quantity)},
    )
    db.commit()
    return {
        "product_id": product_id,
        "warehouse_id": warehouse_id,
        "safe_quantity": str(safe_quantity),
    }
