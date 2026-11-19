from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINANCE_RECORD_CREATOR_POSITIONS
from app.core.errors import AppError
from app.models.business import CashFlow, Customer, FinanceRecord, Supplier
from app.schemas.business import CashFlowCreate, FinanceRecordCreate, OrderReview, OrderVoid
from app.services.doc_no import next_doc_no
from app.services.log_service import write_log_safely
from app.services.mock_service import ensure_mock_writable
from app.services.permission_service import Principal, require_permission


def _approved_record(
    db: Session,
    principal: Principal,
    *,
    record_type: str,
    amount: Decimal,
    record_date,
    department_id: int | None,
    counterparty_type: str,
    counterparty_id: int | None,
    source_type: str,
    source_id: int,
) -> FinanceRecord:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return FinanceRecord(
        record_no=next_doc_no(db, "FR", "FR"),
        record_type=record_type,
        amount=amount,
        record_date=record_date,
        accounting_period=f"{record_date:%Y-%m}",
        counterparty_type=counterparty_type,
        counterparty_id=counterparty_id,
        source_type=source_type,
        source_id=source_id,
        department_id=department_id,
        status="approved",
        created_by=principal.user_id,
        reviewer_id=principal.user_id,
        reviewed_at=now,
    )


def generate_sales_approval(
    db: Session,
    principal: Principal,
    *,
    order_id: int,
    amount: Decimal,
    order_date,
    department_id: int | None,
    customer_id: int,
) -> None:
    exists = db.scalar(
        select(FinanceRecord.id).where(
            FinanceRecord.source_type == "sales_order",
            FinanceRecord.source_id == order_id,
            FinanceRecord.record_type == "receivable",
        )
    )
    if exists is not None:
        return
    # 销售单审核只确认应收；收入在出库审核通过时确认，避免未发货即确认收入。
    db.add(
        _approved_record(
            db,
            principal,
            record_type="receivable",
            amount=amount,
            record_date=order_date,
            department_id=department_id,
            counterparty_type="customer",
            counterparty_id=customer_id,
            source_type="sales_order",
            source_id=order_id,
        )
    )


def generate_purchase_approval(
    db: Session,
    principal: Principal,
    *,
    order_id: int,
    amount: Decimal,
    order_date,
    department_id: int | None,
    supplier_id: int,
) -> None:
    exists = db.scalar(
        select(FinanceRecord.id).where(
            FinanceRecord.source_type == "purchase_order",
            FinanceRecord.source_id == order_id,
            FinanceRecord.record_type == "payable",
        )
    )
    if exists is not None:
        return
    db.add(
        _approved_record(
            db,
            principal,
            record_type="payable",
            amount=amount,
            record_date=order_date,
            department_id=department_id,
            counterparty_type="supplier",
            counterparty_id=supplier_id,
            source_type="purchase_order",
            source_id=order_id,
        )
    )


def generate_stock_cost(
    db: Session,
    principal: Principal,
    *,
    movement_id: int,
    amount: Decimal,
    record_date,
    department_id: int | None,
    supplier_id: int | None,
) -> None:
    if amount <= 0:
        return
    exists = db.scalar(
        select(FinanceRecord.id).where(
            FinanceRecord.source_type == "stock_movement",
            FinanceRecord.source_id == movement_id,
            FinanceRecord.record_type == "cost",
        )
    )
    if exists is not None:
        return
    db.add(
        _approved_record(
            db,
            principal,
            record_type="cost",
            amount=amount,
            record_date=record_date,
            department_id=department_id,
            counterparty_type="supplier" if supplier_id else "none",
            counterparty_id=supplier_id,
            source_type="stock_movement",
            source_id=movement_id,
        )
    )


def generate_sales_shipping(
    db: Session,
    principal: Principal,
    *,
    movement_id: int,
    income: Decimal,
    cost: Decimal,
    record_date,
    department_id: int | None,
    customer_id: int | None,
) -> None:
    """销售出库审核通过：确认收入并结转成本（按出入库单幂等）。"""
    entries = (
        ("income", income, "customer", customer_id),
        ("cost", cost, "none", None),
    )
    for record_type, amount, counterparty_type, counterparty_id in entries:
        if amount <= 0:
            continue
        exists = db.scalar(
            select(FinanceRecord.id).where(
                FinanceRecord.source_type == "stock_movement",
                FinanceRecord.source_id == movement_id,
                FinanceRecord.record_type == record_type,
            )
        )
        if exists is not None:
            continue
        db.add(
            _approved_record(
                db,
                principal,
                record_type=record_type,
                amount=amount,
                record_date=record_date,
                department_id=department_id,
                counterparty_type=counterparty_type,
                counterparty_id=counterparty_id,
                source_type="stock_movement",
                source_id=movement_id,
            )
        )


def generate_return_records(
    db: Session,
    principal: Principal,
    *,
    movement_id: int,
    income_reversal: Decimal = Decimal("0"),
    cost_reversal: Decimal = Decimal("0"),
    record_date,
    department_id: int | None,
    counterparty_type: str,
    counterparty_id: int | None,
) -> None:
    """退货审核通过：生成红字财务记录（按出入库单幂等）。"""
    entries = (
        ("income_reversal", income_reversal, counterparty_type, counterparty_id),
        ("cost_reversal", cost_reversal, "none", None),
    )
    for record_type, amount, cp_type, cp_id in entries:
        if amount <= 0:
            continue
        exists = db.scalar(
            select(FinanceRecord.id).where(
                FinanceRecord.source_type == "stock_movement",
                FinanceRecord.source_id == movement_id,
                FinanceRecord.record_type == record_type,
            )
        )
        if exists is not None:
            continue
        db.add(
            _approved_record(
                db,
                principal,
                record_type=record_type,
                amount=amount,
                record_date=record_date,
                department_id=department_id,
                counterparty_type=cp_type,
                counterparty_id=cp_id,
                source_type="stock_movement",
                source_id=movement_id,
            )
        )


def void_by_source(db: Session, source_type: str, source_id: int, reason: str) -> None:
    records = db.scalars(
        select(FinanceRecord).where(
            FinanceRecord.source_type == source_type,
            FinanceRecord.source_id == source_id,
            FinanceRecord.status != "void",
            FinanceRecord.deleted_at.is_(None),
        )
    ).all()
    for record in records:
        record.status = "void"
        record.void_reason = reason


def generate_work_order_expense(
    db: Session,
    principal: Principal,
    *,
    order_id: int,
    amount: Decimal,
    department_id: int | None,
) -> None:
    """报销工单审核通过生成唯一费用记录（幂等）。"""
    if amount <= 0:
        return
    exists = db.scalar(
        select(FinanceRecord.id).where(
            FinanceRecord.source_type == "work_order",
            FinanceRecord.source_id == order_id,
            FinanceRecord.record_type == "expense",
        )
    )
    if exists is not None:
        return
    db.add(
        _approved_record(
            db,
            principal,
            record_type="expense",
            amount=amount,
            record_date=_today(),
            department_id=department_id,
            counterparty_type="none",
            counterparty_id=None,
            source_type="work_order",
            source_id=order_id,
        )
    )


# ---------------------------------------------------------------------------
# 手工财务记录与资金流水
# ---------------------------------------------------------------------------


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _record_payload(row: FinanceRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "record_no": row.record_no,
        "record_type": row.record_type,
        "amount": str(row.amount),
        "record_date": row.record_date.isoformat(),
        "accounting_period": row.accounting_period,
        "counterparty_type": row.counterparty_type,
        "counterparty_id": row.counterparty_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "account_subject": row.account_subject,
        "department_id": row.department_id,
        "status": row.status,
        "created_by": row.created_by,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "void_reason": row.void_reason,
        "version": row.version,
        "is_mock": row.is_mock,
        "remark": row.remark,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_records(
    db: Session,
    principal: Principal,
    *,
    record_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "read")
    stmt = select(FinanceRecord).where(FinanceRecord.deleted_at.is_(None))
    if record_type:
        stmt = stmt.where(FinanceRecord.record_type == record_type)
    if status:
        stmt = stmt.where(FinanceRecord.status == status)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(FinanceRecord.record_no.ilike(like))
    if start_date is not None:
        stmt = stmt.where(FinanceRecord.record_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(FinanceRecord.record_date <= end_date)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(FinanceRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_record_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_record(db: Session, principal: Principal, record_id: int) -> dict[str, Any]:
    require_permission(principal, "finance_record", "read")
    return _record_payload(_load_record(db, record_id))


def _load_record(db: Session, record_id: int) -> FinanceRecord:
    row = db.get(FinanceRecord, record_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "财务记录不存在或不可见", 404)
    return row


def create_record(
    db: Session, principal: Principal, payload: FinanceRecordCreate
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "create")
    ensure_mock_writable(payload.is_mock)
    if not principal.has_position(*FINANCE_RECORD_CREATOR_POSITIONS):
        raise AppError(2001, "出纳只能录入资金流水", 403)
    if payload.counterparty_type != "none" and payload.counterparty_id is None:
        raise AppError(1001, "缺少往来对象", 400)
    record_date = payload.record_date or _today()
    auto_approved = principal.has_position("finance_head")
    row = FinanceRecord(
        record_no=next_doc_no(db, "FR", "FR"),
        record_type=payload.record_type,
        amount=payload.amount,
        record_date=record_date,
        accounting_period=f"{record_date:%Y-%m}",
        counterparty_type=payload.counterparty_type,
        counterparty_id=payload.counterparty_id,
        source_type="manual",
        account_subject=payload.account_subject,
        department_id=principal.department_id,
        status="approved" if auto_approved else "pending_review",
        reviewer_id=principal.user_id if auto_approved else None,
        reviewed_at=datetime.now(ZoneInfo("Asia/Shanghai")) if auto_approved else None,
        created_by=principal.user_id,
        version=1 if auto_approved else 0,
        is_mock=payload.is_mock,
        remark=payload.remark,
    )
    db.add(row)
    write_log_safely(
        db,
        resource="finance_record",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="finance_record",
        target_id=row.record_no,
        detail={"amount": str(payload.amount), "record_type": payload.record_type},
    )
    db.commit()
    return _record_payload(row)


def review_record(
    db: Session, principal: Principal, record_id: int, payload: OrderReview
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "review")
    row = _load_record(db, record_id)
    if row.status != "pending_review":
        raise AppError(3001, "当前状态不允许审核", 409)
    if row.created_by == principal.user_id:
        raise AppError(3000, "制单人与审核人不能是同一人", 409)
    if row.version != payload.version:
        raise AppError(3002, "记录已被他人更新，请刷新后重试", 409)
    if payload.decision == "reject" and not payload.comment:
        raise AppError(3000, "驳回必须填写意见", 409)
    row.status = "approved" if payload.decision == "approve" else "rejected"
    row.reviewer_id = principal.user_id
    row.reviewed_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    row.version += 1
    write_log_safely(
        db,
        resource="finance_record",
        action="review",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="finance_record",
        target_id=row.record_no,
        detail={"amount": str(row.amount), "result": row.status},
    )
    db.commit()
    return _record_payload(row)


def void_record(
    db: Session, principal: Principal, record_id: int, payload: OrderVoid
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "review")
    row = _load_record(db, record_id)
    if row.status not in ("pending_review", "approved"):
        raise AppError(3001, "仅待审核或已通过的记录可作废", 409)
    if row.version != payload.version:
        raise AppError(3002, "记录已被他人更新，请刷新后重试", 409)
    row.status = "void"
    row.void_reason = payload.reason
    row.version += 1
    write_log_safely(
        db,
        resource="finance_record",
        action="void",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="finance_record",
        target_id=row.record_no,
        detail={"amount": str(row.amount), "reason": payload.reason},
    )
    db.commit()
    return _record_payload(row)


def _flow_payload(row: CashFlow) -> dict[str, Any]:
    return {
        "id": row.id,
        "flow_no": row.flow_no,
        "direction": row.direction,
        "amount": str(row.amount),
        "flow_date": row.flow_date.isoformat(),
        "payment_method": row.payment_method,
        "related_order_type": row.related_order_type,
        "related_order_id": row.related_order_id,
        "status": row.status,
        "department_id": row.department_id,
        "created_by": row.created_by,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "void_reason": row.void_reason,
        "version": row.version,
        "is_mock": row.is_mock,
        "remark": row.remark,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_cash_flows(
    db: Session,
    principal: Principal,
    *,
    direction: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "read")
    stmt = select(CashFlow).where(CashFlow.deleted_at.is_(None))
    if direction:
        stmt = stmt.where(CashFlow.direction == direction)
    if status:
        stmt = stmt.where(CashFlow.status == status)
    if start_date is not None:
        stmt = stmt.where(CashFlow.flow_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(CashFlow.flow_date <= end_date)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(CashFlow.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_flow_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _load_flow(db: Session, flow_id: int) -> CashFlow:
    row = db.get(CashFlow, flow_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "资金流水不存在或不可见", 404)
    return row


def get_cash_flow(db: Session, principal: Principal, flow_id: int) -> dict[str, Any]:
    require_permission(principal, "finance_record", "read")
    return _flow_payload(_load_flow(db, flow_id))


def create_cash_flow(db: Session, principal: Principal, payload: CashFlowCreate) -> dict[str, Any]:
    require_permission(principal, "finance_record", "create")
    ensure_mock_writable(payload.is_mock)
    flow_date = payload.flow_date or _today()
    auto_approved = principal.has_position("finance_head")
    row = CashFlow(
        flow_no=next_doc_no(db, "CF", "CF"),
        direction=payload.direction,
        amount=payload.amount,
        flow_date=flow_date,
        payment_method=payload.payment_method,
        related_order_type=payload.related_order_type,
        related_order_id=payload.related_order_id,
        status="approved" if auto_approved else "pending_review",
        reviewer_id=principal.user_id if auto_approved else None,
        reviewed_at=datetime.now(ZoneInfo("Asia/Shanghai")) if auto_approved else None,
        department_id=principal.department_id,
        created_by=principal.user_id,
        version=1 if auto_approved else 0,
        is_mock=payload.is_mock,
        remark=payload.remark,
    )
    db.add(row)
    write_log_safely(
        db,
        resource="finance_record",
        action="create_cash_flow",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="cash_flow",
        target_id=row.flow_no,
        detail={"amount": str(payload.amount), "direction": payload.direction},
    )
    db.commit()
    return _flow_payload(row)


def review_cash_flow(
    db: Session, principal: Principal, flow_id: int, payload: OrderReview
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "review")
    row = _load_flow(db, flow_id)
    if row.status != "pending_review":
        raise AppError(3001, "当前状态不允许审核", 409)
    if row.created_by == principal.user_id:
        raise AppError(3000, "制单人与审核人不能是同一人", 409)
    if row.version != payload.version:
        raise AppError(3002, "记录已被他人更新，请刷新后重试", 409)
    if payload.decision == "reject" and not payload.comment:
        raise AppError(3000, "驳回必须填写意见", 409)
    row.status = "approved" if payload.decision == "approve" else "rejected"
    row.reviewer_id = principal.user_id
    row.reviewed_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    row.version += 1
    write_log_safely(
        db,
        resource="finance_record",
        action="review_cash_flow",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="cash_flow",
        target_id=row.flow_no,
        detail={"amount": str(row.amount), "result": row.status},
    )
    db.commit()
    return _flow_payload(row)


def void_cash_flow(
    db: Session, principal: Principal, flow_id: int, payload: OrderVoid
) -> dict[str, Any]:
    require_permission(principal, "finance_record", "review")
    row = _load_flow(db, flow_id)
    if row.status not in ("pending_review", "approved"):
        raise AppError(3001, "仅待审核或已通过的流水可作废", 409)
    if row.version != payload.version:
        raise AppError(3002, "记录已被他人更新，请刷新后重试", 409)
    row.status = "void"
    row.void_reason = payload.reason
    row.version += 1
    write_log_safely(
        db,
        resource="finance_record",
        action="void_cash_flow",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="cash_flow",
        target_id=row.flow_no,
        detail={"amount": str(row.amount), "reason": payload.reason},
    )
    db.commit()
    return _flow_payload(row)


def receivable_payable_detail(
    db: Session,
    principal: Principal,
    *,
    record_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """应收应付明细（未核销口径：全部已审核金额），供页面与 Agent 共用。"""
    require_permission(principal, "finance_record", "read")
    allowed = ("receivable", "payable")
    types = [record_type] if record_type in allowed else list(allowed)
    stmt = select(FinanceRecord).where(
        FinanceRecord.status == "approved",
        FinanceRecord.deleted_at.is_(None),
        FinanceRecord.record_type.in_(types),
    )
    if start_date is not None:
        stmt = stmt.where(FinanceRecord.record_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(FinanceRecord.record_date <= end_date)
    rows = db.scalars(
        stmt.order_by(FinanceRecord.record_date.desc(), FinanceRecord.id.desc())
    ).all()

    customer_ids = {row.counterparty_id for row in rows if row.counterparty_type == "customer"}
    supplier_ids = {row.counterparty_id for row in rows if row.counterparty_type == "supplier"}
    names: dict[tuple[str, int], str] = {}
    if customer_ids:
        names.update(
            {
                ("customer", item_id): name
                for item_id, name in db.execute(
                    select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
                ).all()
            }
        )
    if supplier_ids:
        names.update(
            {
                ("supplier", item_id): name
                for item_id, name in db.execute(
                    select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids))
                ).all()
            }
        )

    totals = {"receivable": Decimal("0"), "payable": Decimal("0")}
    items = []
    for row in rows:
        totals[row.record_type] = totals.get(row.record_type, Decimal("0")) + row.amount
        items.append(
            {
                "record_no": row.record_no,
                "record_type": row.record_type,
                "amount": str(row.amount),
                "record_date": row.record_date.isoformat(),
                "counterparty_type": row.counterparty_type,
                "counterparty_id": row.counterparty_id,
                "counterparty_name": names.get((row.counterparty_type, row.counterparty_id)),
                "source_type": row.source_type,
                "source_id": row.source_id,
                "status": row.status,
            }
        )
    return {
        "receivable_total": str(totals["receivable"].quantize(Decimal("0.01"))),
        "payable_total": str(totals["payable"].quantize(Decimal("0.01"))),
        "items": items[: max(limit, 1)],
        "total": len(items),
    }


AGING_BUCKETS = ("0-30", "31-60", "61-90", "90+")


def _aging_bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def receivable_payable_aging(
    db: Session,
    principal: Principal,
    *,
    record_type: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """应收应付账龄（未核销口径）：按单据日期距截止日的天数分档。"""
    require_permission(principal, "finance_record", "read")
    as_of = as_of or _today()
    allowed = ("receivable", "payable")
    types = [record_type] if record_type in allowed else list(allowed)
    rows = db.scalars(
        select(FinanceRecord).where(
            FinanceRecord.status == "approved",
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.record_type.in_(types),
            FinanceRecord.record_date <= as_of,
        )
    ).all()

    customer_ids = {row.counterparty_id for row in rows if row.counterparty_type == "customer"}
    supplier_ids = {row.counterparty_id for row in rows if row.counterparty_type == "supplier"}
    names: dict[tuple[str, int], str] = {}
    if customer_ids:
        names.update(
            {
                ("customer", item_id): name
                for item_id, name in db.execute(
                    select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
                ).all()
            }
        )
    if supplier_ids:
        names.update(
            {
                ("supplier", item_id): name
                for item_id, name in db.execute(
                    select(Supplier.id, Supplier.name).where(Supplier.id.in_(supplier_ids))
                ).all()
            }
        )

    empty_bucket = {key: Decimal("0") for key in AGING_BUCKETS}
    summary = {record_type_value: dict(empty_bucket) for record_type_value in allowed}
    partners: dict[tuple[str, str, int | None], dict[str, Any]] = {}
    for row in rows:
        days = (as_of - row.record_date).days
        bucket = _aging_bucket(days)
        summary[row.record_type][bucket] += row.amount
        key = (row.record_type, row.counterparty_type, row.counterparty_id)
        partner = partners.setdefault(
            key,
            {
                "record_type": row.record_type,
                "counterparty_type": row.counterparty_type,
                "counterparty_id": row.counterparty_id,
                "counterparty_name": names.get((row.counterparty_type, row.counterparty_id)),
                "total": Decimal("0"),
                **{name: Decimal("0") for name in AGING_BUCKETS},
            },
        )
        partner[bucket] += row.amount
        partner["total"] += row.amount

    def _format(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: (str(value.quantize(Decimal("0.01"))) if isinstance(value, Decimal) else value)
            for key, value in row.items()
        }

    partner_rows = sorted(
        (_format(item) for item in partners.values()),
        key=lambda item: Decimal(item["total"]),
        reverse=True,
    )
    return {
        "as_of": as_of.isoformat(),
        "receivable": _format(summary["receivable"]),
        "payable": _format(summary["payable"]),
        "items": partner_rows,
        "total": len(partner_rows),
    }
