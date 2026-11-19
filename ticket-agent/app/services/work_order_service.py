"""工单业务：创建、补充、分配、处理、审核、撤回、转交、查询。

状态变化全部委托 `flow_service.transition`；这里只做参数整理、明细表写入
和查询组织。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.constants import (
    CATEGORY_CREATOR_POSITIONS,
    CATEGORY_DEVICE_REPAIR,
    CATEGORY_EXPENSE_REIMBURSEMENT,
    CATEGORY_REVIEWER_POSITION,
    CATEGORY_SECURITY_PATROL,
    CATEGORY_TRANSPORT_EXCEPTION,
    SCOPE_COMPANY,
    STATUS_PENDING_ASSIGNMENT,
    STATUS_PENDING_PROCESS,
    STATUS_REJECTED,
    STATUS_SUPPLEMENTING,
)
from app.core.errors import AppError
from app.models.misc import SystemConfig
from app.models.work_order import (
    Device,
    WorkOrder,
    WorkOrderApproval,
    WorkOrderAttachment,
    WorkOrderCategory,
    WorkOrderDevice,
    WorkOrderExpense,
    WorkOrderPatrol,
    WorkOrderRecord,
    WorkOrderTransport,
)
from app.schemas.work_order import (
    AssignIn,
    RecallIn,
    ReviewIn,
    SubmitIn,
    SupplementIn,
    TransferDecisionIn,
    TransferIn,
    WorkOrderCreate,
)
from app.services.agent_context import current_agent_context
from app.services.flow_service import (
    compute_due_at,
    position_snapshot,
    resolve_position_user,
    transition,
)
from app.services.log_service import write_log_safely
from app.services.permission_service import Principal, require_permission
from app.services.scope import apply_work_order_scope

SHANGHAI = ZoneInfo("Asia/Shanghai")

DETAIL_MODEL: dict[str, type] = {
    CATEGORY_DEVICE_REPAIR: WorkOrderDevice,
    CATEGORY_EXPENSE_REIMBURSEMENT: WorkOrderExpense,
    CATEGORY_SECURITY_PATROL: WorkOrderPatrol,
    CATEGORY_TRANSPORT_EXCEPTION: WorkOrderTransport,
}

DETAIL_COLUMNS: dict[str, tuple[str, ...]] = {
    CATEGORY_DEVICE_REPAIR: (
        "device_id",
        "device_no_snapshot",
        "device_name_snapshot",
        "fault_description",
        "repair_result",
    ),
    CATEGORY_EXPENSE_REIMBURSEMENT: ("expense_type", "amount"),
    CATEGORY_SECURITY_PATROL: ("patrol_area", "hazard_description", "rectification_result"),
    CATEGORY_TRANSPORT_EXCEPTION: ("trip_no", "exception_type", "handling_result"),
}

RESULT_FIELD: dict[str, str] = {
    CATEGORY_DEVICE_REPAIR: "repair_result",
    CATEGORY_SECURITY_PATROL: "rectification_result",
    CATEGORY_TRANSPORT_EXCEPTION: "handling_result",
}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _active_category(db: Session, code: str) -> WorkOrderCategory:
    category = db.scalar(
        select(WorkOrderCategory).where(
            WorkOrderCategory.code == code,
            WorkOrderCategory.is_active.is_(True),
        )
    )
    if category is None:
        raise AppError(1001, "工单类别不存在或已停用", 400)
    return category


def _require_creator_position(category: str, principal: Principal) -> None:
    allowed = CATEGORY_CREATOR_POSITIONS.get(category)
    if allowed is not None and not principal.has_position(*allowed):
        raise AppError(3000, "当前岗位不能创建该类工单", 403)


def next_order_no(db: Session) -> str:
    prefix = str(
        db.scalar(
            select(SystemConfig.config_value).where(
                SystemConfig.config_key == "work_order.order_no.prefix"
            )
        )
        or "WO"
    )
    biz_date = datetime.now(SHANGHAI).date()
    seq = db.execute(
        text(
            """
            insert into order_no_sequences (seq_type, seq_date, current_seq)
            values ('WO', :d, 1)
            on conflict (seq_type, seq_date)
            do update set current_seq = order_no_sequences.current_seq + 1, updated_at = now()
            returning current_seq
            """
        ),
        {"d": biz_date},
    ).scalar_one()
    if seq > 9999:
        raise AppError(3000, "当日工单号已用尽", 409)
    return f"{prefix}{biz_date:%Y%m%d}{int(seq):04d}"


def _payload_detail_values(category: str, payload: Any) -> dict[str, Any]:
    group = {
        CATEGORY_DEVICE_REPAIR: payload.device,
        CATEGORY_EXPENSE_REIMBURSEMENT: payload.expense,
        CATEGORY_SECURITY_PATROL: payload.patrol,
        CATEGORY_TRANSPORT_EXCEPTION: payload.transport,
    }.get(category)
    return group.model_dump(exclude_none=True) if group is not None else {}


def _device_snapshot(db: Session, device_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    device = db.get(Device, device_id)
    if device is None or device.deleted_at is not None:
        raise AppError(3000, "设备不存在", 400)
    detail = {
        "device_id": device.id,
        "device_no_snapshot": device.device_no,
        "device_name_snapshot": device.device_name,
    }
    source = {"source_type": "device", "source_id": device.id, "source_name": device.device_name}
    return detail, source


def _missing_fields(category: str, description: str | None, detail: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not description:
        missing.append("description")
    if category == CATEGORY_DEVICE_REPAIR:
        if not detail.get("device_id"):
            missing.append("device_id")
        if not detail.get("fault_description"):
            missing.append("fault_description")
    elif category == CATEGORY_EXPENSE_REIMBURSEMENT:
        if not detail.get("expense_type"):
            missing.append("expense_type")
        if detail.get("amount") is None:
            missing.append("amount")
    elif category == CATEGORY_SECURITY_PATROL:
        if not detail.get("patrol_area"):
            missing.append("patrol_area")
    elif category == CATEGORY_TRANSPORT_EXCEPTION:
        if not detail.get("trip_no"):
            missing.append("trip_no")
        if not detail.get("exception_type"):
            missing.append("exception_type")
    return missing


def _detail_row(db: Session, order: WorkOrder) -> Any:
    model = DETAIL_MODEL.get(order.category)
    if model is None:
        return None
    return db.scalar(select(model).where(model.work_order_id == order.id))


def _detail_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data: dict[str, Any] = {}
    category = getattr(row, "__tablename__", "")
    mapping = {
        "work_order_device": DETAIL_COLUMNS[CATEGORY_DEVICE_REPAIR],
        "work_order_expense": DETAIL_COLUMNS[CATEGORY_EXPENSE_REIMBURSEMENT],
        "work_order_patrol": DETAIL_COLUMNS[CATEGORY_SECURITY_PATROL],
        "work_order_transport": DETAIL_COLUMNS[CATEGORY_TRANSPORT_EXCEPTION],
    }[category]
    for column in mapping:
        value = getattr(row, column)
        data[column] = str(value) if column == "amount" and value is not None else value
    return data


def _order_dict(order: WorkOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "category": order.category,
        "title": order.title,
        "description": order.description,
        "priority": order.priority,
        "status": order.status,
        "source_type": order.source_type,
        "source_id": order.source_id,
        "source_name": order.source_name,
        "department_id": order.department_id,
        "creator_id": order.creator_id,
        "assignee_id": order.assignee_id,
        "reviewer_id": order.reviewer_id,
        "assigned_at": _iso(order.assigned_at),
        "due_at": _iso(order.due_at),
        "is_overdue": order.is_overdue,
        "overdue_at": _iso(order.overdue_at),
        "started_at": _iso(order.started_at),
        "submitted_at": _iso(order.submitted_at),
        "completed_at": _iso(order.completed_at),
        "cancelled_at": _iso(order.cancelled_at),
        "recall_reason": order.recall_reason,
        "transfer_to_id": order.transfer_to_id,
        "transfer_status": order.transfer_status,
        "version": order.version,
        "created_at": _iso(order.created_at),
        "updated_at": _iso(order.updated_at),
    }


def _record_dict(row: WorkOrderRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "action": row.action,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "operator_position": row.operator_position,
        "content": row.content,
        "comment": row.comment,
        "detail": row.detail,
        "created_at": _iso(row.created_at),
    }


def _approval_dict(row: WorkOrderApproval) -> dict[str, Any]:
    return {
        "id": row.id,
        "review_round": row.review_round,
        "reviewer_id": row.reviewer_id,
        "reviewer_name": row.reviewer_name,
        "result": row.result,
        "comment": row.comment,
        "created_at": _iso(row.created_at),
    }


def _detail_payload(db: Session, order: WorkOrder) -> dict[str, Any]:
    data = _order_dict(order)
    data["detail"] = _detail_dict(_detail_row(db, order))
    records = db.scalars(
        select(WorkOrderRecord)
        .where(WorkOrderRecord.work_order_id == order.id)
        .order_by(WorkOrderRecord.created_at, WorkOrderRecord.id)
    ).all()
    approvals = db.scalars(
        select(WorkOrderApproval)
        .where(WorkOrderApproval.work_order_id == order.id)
        .order_by(WorkOrderApproval.review_round)
    ).all()
    data["records"] = [_record_dict(row) for row in records]
    data["approvals"] = [_approval_dict(row) for row in approvals]
    attachments = db.scalars(
        select(WorkOrderAttachment)
        .where(
            WorkOrderAttachment.work_order_id == order.id,
            WorkOrderAttachment.deleted_at.is_(None),
        )
        .order_by(WorkOrderAttachment.created_at, WorkOrderAttachment.id)
    ).all()
    data["attachments"] = [
        {
            "id": item.id,
            "file_name": item.file_name,
            "file_size": item.file_size,
            "mime_type": item.mime_type,
            "uploaded_by": item.uploaded_by,
            "created_at": _iso(item.created_at),
            "download_url": (f"/api/v1/work_orders/{order.id}/attachments/{item.id}/download"),
        }
        for item in attachments
    ]
    return data


def _forced_category(principal: Principal, scope: str) -> str | None:
    """财务负责人按公司范围看工单时，只看报销。"""
    if scope == SCOPE_COMPANY and principal.has_position("finance_head"):
        return CATEGORY_EXPENSE_REIMBURSEMENT
    return None


def _visible_stmt(principal: Principal, *conditions: Any):
    scope = require_permission(principal, "work_order", "read")
    stmt = select(WorkOrder).where(WorkOrder.deleted_at.is_(None), *conditions)
    stmt = apply_work_order_scope(stmt, principal, scope)
    forced = _forced_category(principal, scope)
    if forced is not None:
        stmt = stmt.where(WorkOrder.category == forced)
    return stmt


def visible_order(db: Session, principal: Principal, order_id: int) -> WorkOrder:
    order = db.scalar(_visible_stmt(principal, WorkOrder.id == order_id))
    if order is None:
        raise AppError(3003, "工单不存在或不可见", 404)
    return order


def visible_order_by_no(db: Session, principal: Principal, order_no: str) -> WorkOrder:
    order = db.scalar(_visible_stmt(principal, WorkOrder.order_no == order_no))
    if order is None:
        raise AppError(3003, "工单不存在或不可见", 404)
    return order


def create(db: Session, payload: WorkOrderCreate, principal: Principal) -> dict[str, Any]:
    require_permission(principal, "work_order", "create")
    category = _active_category(db, payload.category)
    _require_creator_position(category.code, principal)

    title = _clean(payload.title)
    if not title:
        raise AppError(1001, "标题必填", 422)
    description = _clean(payload.description)
    detail_values = _payload_detail_values(category.code, payload)
    source_values: dict[str, Any] = {}
    if category.code == CATEGORY_DEVICE_REPAIR and detail_values.get("device_id"):
        resolved, source_values = _device_snapshot(db, detail_values["device_id"])
        detail_values.update(resolved)

    missing = _missing_fields(category.code, description, detail_values)
    now = datetime.now(UTC)

    status = STATUS_SUPPLEMENTING
    reviewer_id = None
    assignee_id = None
    assigned_at = None
    due_at = None
    if not missing:
        if category.code == CATEGORY_EXPENSE_REIMBURSEMENT:
            status = STATUS_PENDING_PROCESS
            assignee_id = principal.user_id
            assigned_at = now
            due_at = compute_due_at(db, category.code, now)
        else:
            status = STATUS_PENDING_ASSIGNMENT
        reviewer_id = resolve_position_user(db, CATEGORY_REVIEWER_POSITION[category.code]).id

    order = WorkOrder(
        order_no=next_order_no(db),
        category=category.code,
        title=title,
        description=description,
        priority=payload.priority,
        status=status,
        department_id=principal.department_id,
        creator_id=principal.user_id,
        assignee_id=assignee_id,
        reviewer_id=reviewer_id,
        assigned_at=assigned_at,
        due_at=due_at,
        version=1,
        **source_values,
    )
    db.add(order)
    db.flush()

    model = DETAIL_MODEL[category.code]
    db.add(model(work_order_id=order.id, **detail_values))
    agent_ctx = current_agent_context()
    db.add(
        WorkOrderRecord(
            work_order_id=order.id,
            action="create",
            from_status=None,
            to_status=status,
            operator_id=principal.user_id,
            operator_name=principal.name,
            operator_position=position_snapshot(principal),
            content="创建工单",
            detail={"missing": missing} if missing else {},
            is_agent=agent_ctx is not None,
            agent_session_id=agent_ctx.session_id if agent_ctx is not None else None,
        )
    )
    write_log_safely(
        db,
        resource="work_order",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="work_order",
        target_id=order.order_no,
        detail={
            "category": category.code,
            "status": status,
            **(
                {"is_agent": True, "agent_session_id": agent_ctx.session_id}
                if agent_ctx is not None
                else {}
            ),
        },
    )
    db.commit()
    db.refresh(order)
    return _detail_payload(db, order)


def list_orders(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "work_order", "read")
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)

    stmt = select(WorkOrder).where(WorkOrder.deleted_at.is_(None))
    stmt = apply_work_order_scope(stmt, principal, scope)

    forced = _forced_category(principal, scope)
    if forced is not None:
        stmt = stmt.where(WorkOrder.category == forced)
    elif category:
        stmt = stmt.where(WorkOrder.category == category)

    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if priority:
        stmt = stmt.where(WorkOrder.priority == priority)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(WorkOrder.order_no.ilike(like), WorkOrder.title.ilike(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_order_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_order(db: Session, principal: Principal, order_id: int) -> dict[str, Any]:
    order = visible_order(db, principal, order_id)
    return _detail_payload(db, order)


def _edit_values(db: Session, order: WorkOrder, payload: SupplementIn) -> dict[str, Any]:
    """把补充/修改后的字段整理成主表写入值，并同步类别明细。"""
    detail_values = _payload_detail_values(order.category, payload)
    source_values: dict[str, Any] = {}
    if order.category == CATEGORY_DEVICE_REPAIR and detail_values.get("device_id"):
        resolved, source_values = _device_snapshot(db, detail_values["device_id"])
        detail_values.update(resolved)

    row = _detail_row(db, order)
    current = (
        {column: getattr(row, column) for column in DETAIL_COLUMNS[order.category]}
        if row is not None
        else {}
    )
    current.update(detail_values)
    description = (
        _clean(payload.description) if payload.description is not None else order.description
    )
    missing = _missing_fields(order.category, description, current)
    if missing:
        raise AppError(3000, f"信息不完整：{'、'.join(missing)}", 400)

    if row is not None:
        for key, value in detail_values.items():
            setattr(row, key, value)
    else:
        db.add(DETAIL_MODEL[order.category](work_order_id=order.id, **detail_values))

    values: dict[str, Any] = dict(source_values)
    values["description"] = description
    if payload.title is not None:
        values["title"] = _clean(payload.title)
    if payload.priority is not None:
        values["priority"] = payload.priority
    return values


def supplement(
    db: Session, principal: Principal, order_id: int, payload: SupplementIn
) -> dict[str, Any]:
    order = visible_order(db, principal, order_id)
    if order.status != STATUS_SUPPLEMENTING:
        raise AppError(3001, "当前状态不允许补充信息", 409)
    if order.creator_id != principal.user_id:
        raise AppError(2004, "只有创建人可以补充信息", 403)

    values = _edit_values(db, order, payload)

    transition(
        db,
        order_id,
        "supplement",
        principal,
        version=payload.version,
        values=values,
    )
    return get_order(db, principal, order_id)


def revise(
    db: Session, principal: Principal, order_id: int, payload: SupplementIn
) -> dict[str, Any]:
    """驳回后由创建人修改工单内容，并重新提交审核。"""
    order = visible_order(db, principal, order_id)
    if order.status != STATUS_REJECTED:
        raise AppError(3001, "当前状态不允许修改工单", 409)
    if order.creator_id != principal.user_id:
        raise AppError(2004, "只有创建人可以修改工单", 403)

    values = _edit_values(db, order, payload)

    transition(
        db,
        order_id,
        "revise",
        principal,
        version=payload.version,
        values=values,
    )
    return get_order(db, principal, order_id)


def assign(
    db: Session, principal: Principal, order_id: int, payload: AssignIn, *, reassign: bool = False
) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    action = "reassign" if reassign else "assign"
    transition(
        db,
        order_id,
        action,
        principal,
        version=payload.version,
        assignee_id=payload.assignee_id,
        comment=payload.comment,
        reassign=reassign,
    )
    return get_order(db, principal, order_id)


def start(db: Session, principal: Principal, order_id: int, version: int) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    transition(db, order_id, "start", principal, version=version)
    return get_order(db, principal, order_id)


def submit(db: Session, principal: Principal, order_id: int, payload: SubmitIn) -> dict[str, Any]:
    order = visible_order(db, principal, order_id)

    result_field = RESULT_FIELD.get(order.category)
    if result_field is not None:
        result_value = _clean(getattr(payload, result_field, None))
        if not result_value:
            raise AppError(1001, "处理结果必填", 422)
        row = _detail_row(db, order)
        if row is None:
            raise AppError(3000, "工单明细缺失", 409)
        setattr(row, result_field, result_value)

    transition(
        db,
        order_id,
        "submit_result",
        principal,
        version=payload.version,
        content=payload.content,
    )
    return get_order(db, principal, order_id)


def review(db: Session, principal: Principal, order_id: int, payload: ReviewIn) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    action = "review_approve" if payload.result == "approve" else "review_reject"
    transition(
        db,
        order_id,
        action,
        principal,
        version=payload.version,
        comment=payload.comment,
    )
    return get_order(db, principal, order_id)


def recall(db: Session, principal: Principal, order_id: int, payload: RecallIn) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    transition(
        db,
        order_id,
        "recall",
        principal,
        version=payload.version,
        reason=payload.reason,
    )
    return get_order(db, principal, order_id)


def transfer(
    db: Session, principal: Principal, order_id: int, payload: TransferIn
) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    transition(
        db,
        order_id,
        "transfer_request",
        principal,
        version=payload.version,
        transfer_to_id=payload.transfer_to_id,
        comment=payload.comment,
    )
    return get_order(db, principal, order_id)


def transfer_decision(
    db: Session, principal: Principal, order_id: int, payload: TransferDecisionIn
) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    action = "transfer_approve" if payload.approve else "transfer_reject"
    transition(
        db,
        order_id,
        action,
        principal,
        version=payload.version,
        comment=payload.comment,
    )
    return get_order(db, principal, order_id)
