"""工单状态机。

所有状态变化只能经过 `transition`：统一做权限、状态、执行人角色校验，按
`version` 乐观锁写入，并在同一事务内写 `work_order_records`（审核动作另写
`work_order_approvals`）。接口层与 Agent 工具都调用这里，禁止直接改 status。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.constants import (
    CATEGORY_ASSIGNEE_POSITIONS,
    CATEGORY_ASSIGNER_POSITION,
    CATEGORY_DUE_HOURS_CONFIG,
    CATEGORY_EXPENSE_REIMBURSEMENT,
    CATEGORY_REVIEWER_POSITION,
    RECALLABLE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PENDING_ASSIGNMENT,
    STATUS_PENDING_PROCESS,
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    STATUS_REJECTED,
    STATUS_SUPPLEMENTING,
)
from app.core.errors import AppError
from app.models.misc import SystemConfig
from app.models.org import Position, User, UserPosition
from app.models.work_order import WorkOrder, WorkOrderApproval, WorkOrderExpense, WorkOrderRecord
from app.services import finance_service
from app.services.agent_context import current_agent_context
from app.services.log_service import write_log_safely
from app.services.notification_service import notify
from app.services.permission_service import Principal, require_permission

# 动作 → (资源, 动作) 权限
ACTION_PERMISSION: dict[str, tuple[str, str]] = {
    "supplement": ("work_order", "update"),
    "assign": ("work_order_assign", "assign"),
    "reassign": ("work_order_assign", "assign"),
    "recall": ("work_order", "update"),
    "start": ("work_order", "update"),
    "submit_result": ("work_order", "update"),
    "revise": ("work_order", "update"),
    "review_approve": ("work_order_review", "review"),
    "review_reject": ("work_order_review", "review"),
    "transfer_request": ("work_order_transfer", "transfer"),
    "transfer_approve": ("work_order_transfer", "transfer"),
    "transfer_reject": ("work_order_transfer", "transfer"),
}


@dataclass(slots=True)
class Outcome:
    """一次流转对主表的写入值，以及要落库的记录内容。"""

    values: dict[str, Any]
    content: str | None = None
    comment: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    approval: str | None = None  # approved / rejected


def get_config_value(db: Session, key: str, default: Any) -> Any:
    value = db.scalar(select(SystemConfig.config_value).where(SystemConfig.config_key == key))
    return default if value is None else value


def get_config_int(db: Session, key: str, default: int) -> int:
    try:
        return int(get_config_value(db, key, default))
    except (TypeError, ValueError):
        return default


def compute_due_at(db: Session, category: str, start: datetime) -> datetime:
    """处理期限 = 分配时间 + 类别期限（小时，读 system_configs）。"""
    key = CATEGORY_DUE_HOURS_CONFIG.get(category)
    hours = get_config_int(db, key, 24) if key else 24
    return start + timedelta(hours=hours)


def resolve_position_user(db: Session, position_code: str) -> User:
    """按岗位找一名在岗用户，用于写入审核人等固定角色。"""
    user = db.scalar(
        select(User)
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
        .order_by(User.id)
        .limit(1)
    )
    if user is None:
        raise AppError(3000, f"岗位 {position_code} 无在岗人员，无法确定审核人", 400)
    return user


def user_has_position(db: Session, user_id: int, codes: frozenset[str]) -> bool:
    hit = db.scalar(
        select(Position.code)
        .join(UserPosition, UserPosition.position_id == Position.id)
        .where(
            UserPosition.user_id == user_id,
            UserPosition.deleted_at.is_(None),
            Position.deleted_at.is_(None),
            Position.is_active.is_(True),
            Position.code.in_(codes),
        )
        .limit(1)
    )
    return hit is not None


def next_review_round(db: Session, work_order_id: int) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(WorkOrderApproval.review_round), 0)).where(
            WorkOrderApproval.work_order_id == work_order_id
        )
    )
    return int(current or 0) + 1


def _load_order(db: Session, order_id: int) -> WorkOrder:
    order = db.get(WorkOrder, order_id)
    if order is None or order.deleted_at is not None:
        raise AppError(3003, "工单不存在或不可见", 404)
    return order


def _require_status(order: WorkOrder, allowed: tuple[str, ...] | set[str]) -> None:
    if order.status not in allowed:
        raise AppError(3001, "当前状态不允许该操作", 409)


def _require_creator(order: WorkOrder, operator: Principal) -> None:
    if order.creator_id != operator.user_id:
        raise AppError(2004, "只有创建人可以执行该操作", 403)


def _require_assignee(order: WorkOrder, operator: Principal) -> None:
    if order.assignee_id != operator.user_id:
        raise AppError(2004, "只有当前处理人可以执行该操作", 403)


def _require_assigner(order: WorkOrder, operator: Principal) -> None:
    required = CATEGORY_ASSIGNER_POSITION.get(order.category)
    if required is None:
        raise AppError(3001, "该类别工单没有分配环节", 409)
    if not operator.has_position(required):
        raise AppError(2001, "无该工单类别的分配权限", 403)


def _require_reviewer(order: WorkOrder, operator: Principal) -> bool:
    """校验审核人；返回是否为总经理代理审核。

    审核人按类别在创建时固定写入 `reviewer_id`，同岗位其他人不能代审；
    只有 `reviewer_id` 为空（历史数据）时才按岗位兜底。
    """
    if order.reviewer_id is not None:
        if order.reviewer_id == operator.user_id:
            return False
        if operator.has_position("general_manager"):
            return True
        raise AppError(2004, "非当前审核人", 403)

    required = CATEGORY_REVIEWER_POSITION.get(order.category)
    if required and operator.has_position(required):
        return False
    if operator.has_position("general_manager"):
        return True
    raise AppError(2004, "非当前审核人", 403)


def _active_user(db: Session, user_id: int, label: str) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or user.status != "active":
        raise AppError(3000, f"{label}不存在或已停用", 400)
    return user


def _require_assignee_position(db: Session, order: WorkOrder, user_id: int) -> None:
    allowed = CATEGORY_ASSIGNEE_POSITIONS.get(order.category)
    if allowed is not None and not user_has_position(db, user_id, allowed):
        raise AppError(3006, "处理人岗位与工单类别不匹配", 400)


def position_snapshot(operator: Principal) -> str:
    return ",".join(sorted(operator.position_codes))[:48]


def _do_supplement(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    _require_status(order, (STATUS_SUPPLEMENTING,))
    _require_creator(order, operator)

    values = dict(kwargs.get("values") or {})
    if order.category == CATEGORY_EXPENSE_REIMBURSEMENT:
        now = datetime.now(UTC)
        values.update(
            status=STATUS_PENDING_PROCESS,
            assignee_id=order.creator_id,
            assigned_at=now,
            due_at=compute_due_at(db, order.category, now),
        )
    else:
        values["status"] = STATUS_PENDING_ASSIGNMENT

    if order.reviewer_id is None and "reviewer_id" not in values:
        values["reviewer_id"] = resolve_position_user(
            db, CATEGORY_REVIEWER_POSITION[order.category]
        ).id
    return Outcome(values=values, content="补充信息")


def _do_assign(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    reassign = bool(kwargs.get("reassign"))
    allowed = (
        (STATUS_PENDING_ASSIGNMENT, STATUS_PENDING_PROCESS)
        if reassign
        else (STATUS_PENDING_ASSIGNMENT,)
    )
    _require_status(order, allowed)
    if reassign and order.started_at is not None:
        raise AppError(3000, "已开始处理的工单不能改派", 409)
    _require_assigner(order, operator)

    assignee = _active_user(db, int(kwargs["assignee_id"]), "处理人")
    _require_assignee_position(db, order, assignee.id)

    now = datetime.now(UTC)
    reviewer_id = (
        order.reviewer_id
        or resolve_position_user(db, CATEGORY_REVIEWER_POSITION[order.category]).id
    )
    return Outcome(
        values={
            "status": STATUS_PENDING_PROCESS,
            "assignee_id": assignee.id,
            "reviewer_id": reviewer_id,
            "assigned_at": now,
            "due_at": compute_due_at(db, order.category, now),
            "is_overdue": False,
            "overdue_at": None,
        },
        comment=kwargs.get("comment"),
        detail={"assignee_id": assignee.id},
    )


def _do_recall(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    _require_status(order, RECALLABLE_STATUSES)
    _require_creator(order, operator)

    reason = (kwargs.get("reason") or "").strip()
    if not reason:
        raise AppError(1001, "撤回原因必填", 422)
    return Outcome(
        values={
            "status": STATUS_CANCELLED,
            "cancelled_at": datetime.now(UTC),
            "recall_reason": reason,
        },
        comment=reason,
    )


def _do_start(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    _require_status(order, (STATUS_PENDING_PROCESS,))
    _require_assignee(order, operator)
    return Outcome(values={"status": STATUS_PROCESSING, "started_at": datetime.now(UTC)})


def _do_submit(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    _require_status(order, (STATUS_PROCESSING,))
    _require_assignee(order, operator)

    content = (kwargs.get("content") or "").strip()
    if not content:
        raise AppError(1001, "处理结果必填", 422)
    return Outcome(
        values={"status": STATUS_PENDING_REVIEW, "submitted_at": datetime.now(UTC)},
        content=content,
    )


def _do_review(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    _require_status(order, (STATUS_PENDING_REVIEW,))
    proxy = _require_reviewer(order, operator)

    approved = bool(kwargs.get("approved"))
    comment = (kwargs.get("comment") or "").strip() or None
    if not approved and not comment:
        raise AppError(1001, "驳回必须填写意见", 422)

    detail = {"proxy_review": True} if proxy else {}
    if approved:
        values = {"status": STATUS_COMPLETED, "completed_at": datetime.now(UTC)}
        result = "approved"
    else:
        values = {"status": STATUS_REJECTED}
        result = "rejected"
    return Outcome(
        values=values,
        comment=comment,
        detail=detail,
        approval=result,
        content=kwargs.get("content"),
    )


def _do_revise(db: Session, order: WorkOrder, operator: Principal, **kwargs: Any) -> Outcome:
    """驳回后创建人修改工单内容，重新进入审核环节。"""
    _require_status(order, (STATUS_REJECTED,))
    _require_creator(order, operator)

    values = dict(kwargs.get("values") or {})
    values.update(status=STATUS_PENDING_REVIEW, submitted_at=datetime.now(UTC))
    return Outcome(values=values, content="修改工单后重新提交")


def _do_transfer_request(
    db: Session, order: WorkOrder, operator: Principal, **kwargs: Any
) -> Outcome:
    _require_status(order, (STATUS_PENDING_PROCESS, STATUS_PROCESSING))
    _require_assignee(order, operator)
    if order.transfer_status == "pending":
        raise AppError(3004, "已有待审核的转交申请", 409)

    target = _active_user(db, int(kwargs["transfer_to_id"]), "转交对象")
    if target.id == order.assignee_id:
        raise AppError(3000, "不能转交给本人", 400)
    _require_assignee_position(db, order, target.id)

    return Outcome(
        values={"transfer_to_id": target.id, "transfer_status": "pending"},
        comment=(kwargs.get("comment") or "").strip() or None,
        detail={"transfer_to_id": target.id},
    )


def _do_transfer_approve(
    db: Session, order: WorkOrder, operator: Principal, **kwargs: Any
) -> Outcome:
    _require_status(order, (STATUS_PENDING_PROCESS, STATUS_PROCESSING))
    _require_reviewer(order, operator)
    if order.transfer_status != "pending" or order.transfer_to_id is None:
        raise AppError(3004, "没有待审核的转交申请", 409)

    now = datetime.now(UTC)
    return Outcome(
        values={
            "status": STATUS_PENDING_PROCESS,
            "assignee_id": order.transfer_to_id,
            "assigned_at": now,
            "due_at": compute_due_at(db, order.category, now),
            "is_overdue": False,
            "overdue_at": None,
            "transfer_status": "approved",
        },
        comment=(kwargs.get("comment") or "").strip() or None,
        detail={"from_assignee_id": order.assignee_id, "to_assignee_id": order.transfer_to_id},
    )


def _do_transfer_reject(
    db: Session, order: WorkOrder, operator: Principal, **kwargs: Any
) -> Outcome:
    _require_status(order, (STATUS_PENDING_PROCESS, STATUS_PROCESSING))
    _require_reviewer(order, operator)
    if order.transfer_status != "pending":
        raise AppError(3004, "没有待审核的转交申请", 409)

    comment = (kwargs.get("comment") or "").strip()
    if not comment:
        raise AppError(1001, "驳回转交必须填写意见", 422)
    return Outcome(
        values={"transfer_status": "rejected"},
        comment=comment,
        detail={"transfer_to_id": order.transfer_to_id},
    )


_HANDLERS: dict[str, Callable[..., Outcome]] = {
    "supplement": _do_supplement,
    "assign": _do_assign,
    "reassign": _do_assign,
    "recall": _do_recall,
    "start": _do_start,
    "submit_result": _do_submit,
    "revise": _do_revise,
    "review_approve": _do_review,
    "review_reject": _do_review,
    "transfer_request": _do_transfer_request,
    "transfer_approve": _do_transfer_approve,
    "transfer_reject": _do_transfer_reject,
}

# 写操作日志用的动作名与级别（规划 9.3.2：重要操作单独标记）
LOG_ACTION: dict[str, str] = {
    "supplement": "supplement",
    "assign": "assign",
    "reassign": "assign",
    "recall": "recall",
    "start": "start",
    "submit_result": "submit",
    "revise": "submit",
    "review_approve": "review",
    "review_reject": "review",
    "transfer_request": "transfer",
    "transfer_approve": "transfer",
    "transfer_reject": "transfer",
}
IMPORTANT_ACTIONS = frozenset(
    {
        "assign",
        "reassign",
        "review_approve",
        "review_reject",
        "transfer_request",
        "transfer_approve",
        "transfer_reject",
    }
)


def _notify_transition(
    db: Session, order: WorkOrder, action: str, outcome: Outcome, operator: Principal
) -> None:
    values = outcome.values
    assignee = values.get("assignee_id", order.assignee_id)
    reviewer = values.get("reviewer_id", order.reviewer_id)
    base = f"{order.order_no} {order.title}"

    def push(user_id: int | None, type_: str, title: str, content: str) -> None:
        if user_id is None or user_id == operator.user_id:
            return
        notify(
            db,
            user_id=user_id,
            type=type_,
            title=title,
            content=content,
            related_id=order.id,
        )

    if action in ("assign", "reassign"):
        push(assignee, "work_order_assigned", "工单已分配", base)
    elif action == "recall":
        push(
            order.assignee_id,
            "work_order_recalled",
            "工单已撤回",
            f"{base}；原因：{outcome.comment or ''}",
        )
    elif action == "submit_result":
        push(reviewer, "work_order_review", "工单待审核", base)
    elif action == "review_approve":
        push(order.creator_id, "work_order_completed", "工单已完成", base)
    elif action == "review_reject":
        tip = f"{base}；意见：{outcome.comment or ''}"
        push(order.creator_id, "work_order_rejected", "工单被驳回，请修改后重新提交", tip)
        if order.assignee_id != order.creator_id:
            push(order.assignee_id, "work_order_rejected", "工单被驳回", tip)
    elif action == "revise":
        push(
            reviewer,
            "work_order_review",
            "工单待审核",
            f"{base}；创建人已修改并重新提交",
        )
    elif action == "transfer_request":
        push(reviewer, "transfer_request", "转交待审核", f"{base}；申请人：{operator.name}")
    elif action == "transfer_approve":
        push(values.get("assignee_id"), "work_order_assigned", "工单已分配", base)
        push(order.assignee_id, "transfer_result", "转交已通过", base)
    elif action == "transfer_reject":
        push(
            order.assignee_id,
            "transfer_result",
            "转交被驳回",
            f"{base}；意见：{outcome.comment or ''}",
        )


def transition(
    db: Session,
    order_id: int,
    action: str,
    operator: Principal,
    *,
    version: int,
    **kwargs: Any,
) -> WorkOrder:
    """执行一次状态流转；`version` 为客户端读到的工单版本。"""
    handler = _HANDLERS.get(action)
    if handler is None:
        raise AppError(3000, f"未知的流转动作：{action}", 400)

    resource, act = ACTION_PERMISSION[action]
    require_permission(operator, resource, act)

    order = _load_order(db, order_id)
    if order.version != version:
        raise AppError(3002, "工单已被他人更新，请刷新后重试", 409)
    from_status = order.status

    if action == "review_approve":
        kwargs["approved"] = True
    elif action == "review_reject":
        kwargs["approved"] = False

    outcome = handler(db, order, operator, **kwargs)
    target_status = outcome.values.get("status", from_status)

    result = db.execute(
        update(WorkOrder)
        .where(WorkOrder.id == order.id, WorkOrder.version == version)
        .values(**outcome.values, version=WorkOrder.version + 1)
    )
    if result.rowcount == 0:
        raise AppError(3002, "工单已被他人更新，请刷新后重试", 409)

    agent_ctx = current_agent_context()
    db.add(
        WorkOrderRecord(
            work_order_id=order.id,
            action=action,
            from_status=from_status,
            to_status=target_status,
            operator_id=operator.user_id,
            operator_name=operator.name,
            operator_position=position_snapshot(operator),
            content=outcome.content,
            comment=outcome.comment,
            detail=outcome.detail,
            is_agent=agent_ctx is not None,
            agent_session_id=agent_ctx.session_id if agent_ctx is not None else None,
        )
    )
    if outcome.approval is not None:
        db.add(
            WorkOrderApproval(
                work_order_id=order.id,
                review_round=next_review_round(db, order.id),
                reviewer_id=operator.user_id,
                reviewer_name=operator.name,
                result=outcome.approval,
                comment=outcome.comment,
            )
        )

    write_log_safely(
        db,
        resource="work_order",
        action=LOG_ACTION.get(action, action),
        user_id=operator.user_id,
        user_name=operator.name,
        department_id=operator.department_id,
        log_level="important" if action in IMPORTANT_ACTIONS else "normal",
        target_type="work_order",
        target_id=order.order_no,
        detail={
            "category": order.category,
            "from_status": from_status,
            "to_status": target_status,
            **(
                {"is_agent": True, "agent_session_id": agent_ctx.session_id}
                if agent_ctx is not None
                else {}
            ),
        },
    )
    _notify_transition(db, order, action, outcome, operator)

    if action == "review_approve" and order.category == CATEGORY_EXPENSE_REIMBURSEMENT:
        amount = db.scalar(
            select(WorkOrderExpense.amount).where(WorkOrderExpense.work_order_id == order.id)
        )
        if amount is not None:
            finance_service.generate_work_order_expense(
                db,
                operator,
                order_id=order.id,
                amount=Decimal(amount),
                department_id=order.department_id,
            )

    db.commit()
    db.refresh(order)
    return order
