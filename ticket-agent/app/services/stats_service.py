"""工单基础统计：数量、处理时长、完成率、重复问题、超时。

口径（无更细规定时的落地方式）：
- 数量按创建时间落在统计区间内、未删除的工单统计。
- 处理时长 = completed_at - assigned_at，只统计已完成且两时间齐全的工单，单位小时。
- 完成率 = 已完成数 / 区间内工单总数；无工单时为 0。
- 重复问题按 `work_order.repeat.period_days` 回溯，
  按“同一设备（source_id）或同类故障（标题）”分组，组内 >= 2 计为重复。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.constants import ALL_CATEGORIES
from app.core.errors import AppError
from app.models.work_order import WorkOrder
from app.services import metric_service
from app.services.flow_service import get_config_int
from app.services.permission_service import Principal, require_permission
from app.services.scope import apply_work_order_scope


def finance_trend(db: Session, principal: Principal, months: int = 6) -> dict[str, Any]:
    require_permission(principal, "report", "read")
    return metric_service.finance_trend(db, max(1, min(months, 36)))


def _filters(
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    category: str | None,
    department_id: int | None,
    assignee_id: int | None,
) -> list[Any]:
    conditions: list[Any] = [WorkOrder.deleted_at.is_(None)]
    if start_at is not None:
        conditions.append(WorkOrder.created_at >= start_at)
    if end_at is not None:
        conditions.append(WorkOrder.created_at <= end_at)
    if category is not None:
        conditions.append(WorkOrder.category == category)
    if department_id is not None:
        conditions.append(WorkOrder.department_id == department_id)
    if assignee_id is not None:
        conditions.append(WorkOrder.assignee_id == assignee_id)
    return conditions


def work_order_stats(
    db: Session,
    principal: Principal,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    category: str | None = None,
    department_id: int | None = None,
    assignee_id: int | None = None,
) -> dict[str, Any]:
    scope = require_permission(principal, "report", "read")
    if start_at and end_at and start_at > end_at:
        raise AppError(1003, "开始时间不能晚于结束时间", 400)
    if category is not None and category not in ALL_CATEGORIES:
        raise AppError(1003, "工单类别不存在", 400)

    conditions = _filters(
        start_at=start_at,
        end_at=end_at,
        category=category,
        department_id=department_id,
        assignee_id=assignee_id,
    )
    base = select(WorkOrder).where(*conditions)
    base = apply_work_order_scope(base, principal, scope)
    scoped = base.subquery()

    status_rows = db.execute(select(scoped.c.status, func.count()).group_by(scoped.c.status)).all()
    category_rows = db.execute(
        select(scoped.c.category, func.count()).group_by(scoped.c.category)
    ).all()

    total = db.scalar(select(func.count()).select_from(scoped)) or 0
    completed = (
        db.scalar(select(func.count()).select_from(scoped).where(scoped.c.status == "completed"))
        or 0
    )
    overdue = (
        db.scalar(select(func.count()).select_from(scoped).where(scoped.c.is_overdue.is_(True)))
        or 0
    )

    duration_hours = db.scalar(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    scoped.c.completed_at - scoped.c.assigned_at,
                )
                / 3600
            )
        ).where(
            and_(
                scoped.c.status == "completed",
                scoped.c.completed_at.is_not(None),
                scoped.c.assigned_at.is_not(None),
            )
        )
    )

    repeat = _repeat_stats(
        db,
        principal,
        scope,
        start_at=start_at,
        end_at=end_at,
        category=category,
        department_id=department_id,
        assignee_id=assignee_id,
    )

    return {
        "range": {
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
        },
        "total": total,
        "completed": completed,
        "completion_rate": round(completed / total, 4) if total else None,
        "avg_process_hours": round(float(duration_hours), 2)
        if duration_hours is not None
        else None,
        "avg_process_minutes": round(float(duration_hours) * 60, 1)
        if duration_hours is not None
        else None,
        "overdue": overdue,
        "overdue_rate": round(overdue / total, 4) if total else None,
        "by_status": {row[0]: row[1] for row in status_rows},
        "by_category": {row[0]: row[1] for row in category_rows},
        "repeat": repeat,
    }


def _repeat_stats(
    db: Session,
    principal: Principal,
    scope: str,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    category: str | None,
    department_id: int | None,
    assignee_id: int | None,
) -> dict[str, Any]:
    period_days = get_config_int(db, "work_order.repeat.period_days", 30)
    window_end = end_at or datetime.now(UTC)
    window_start = window_end - timedelta(days=period_days)
    effective_start = max(start_at, window_start) if start_at else window_start

    key = func.coalesce(sa.cast(WorkOrder.source_id, sa.String), WorkOrder.title)
    conditions = _filters(
        start_at=effective_start,
        end_at=window_end,
        category=category,
        department_id=department_id,
        assignee_id=assignee_id,
    )
    stmt = (
        select(WorkOrder.category, key.label("group_key"), func.count().label("cnt"))
        .where(*conditions)
        .group_by(WorkOrder.category, key)
        .having(func.count() >= 2)
        .order_by(func.count().desc(), key)
        .limit(20)
    )
    stmt = apply_work_order_scope(stmt, principal, scope)
    rows = db.execute(stmt).all()
    return {
        "period_days": period_days,
        "order_count": sum(row.cnt for row in rows),
        "groups": [
            {"category": row.category, "key": row.group_key, "count": row.cnt} for row in rows
        ],
    }


_GRANULARITY = {"day", "week", "month"}


def work_order_trend(
    db: Session,
    principal: Principal,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    granularity: str = "day",
    category: str | None = None,
    department_id: int | None = None,
) -> dict[str, Any]:
    """按日/周/月汇总创建量、完成量与超时量，补齐空区间为 0。"""
    scope = require_permission(principal, "work_order", "read")
    if granularity not in _GRANULARITY:
        raise AppError(1003, "粒度只支持 day/week/month", 400)
    if category is not None and category not in ALL_CATEGORIES:
        raise AppError(1003, "工单类别不存在", 400)
    now = datetime.now(UTC)
    effective_end = end_at or now
    effective_start = start_at or (effective_end - timedelta(days=30))
    if effective_start > effective_end:
        raise AppError(1003, "开始时间不能晚于结束时间", 400)

    conditions = _filters(
        start_at=effective_start,
        end_at=effective_end,
        category=category,
        department_id=department_id,
        assignee_id=None,
    )
    base = apply_work_order_scope(select(WorkOrder).where(*conditions), principal, scope)
    scoped = base.subquery()
    period = func.date_trunc(sa.literal(granularity), scoped.c.created_at)

    created_rows = db.execute(
        select(period.label("period"), func.count()).group_by(period).order_by(period)
    ).all()
    completed_rows = db.execute(
        select(period.label("period"), func.count())
        .where(scoped.c.status == "completed", scoped.c.completed_at.is_not(None))
        .group_by(period)
        .order_by(period)
    ).all()
    overdue_rows = db.execute(
        select(period.label("period"), func.count())
        .where(scoped.c.is_overdue.is_(True))
        .group_by(period)
        .order_by(period)
    ).all()

    buckets: dict[str, dict[str, int]] = {}
    for label, rows in (
        ("created", created_rows),
        ("completed", completed_rows),
        ("overdue", overdue_rows),
    ):
        for row in rows:
            key = row[0].date().isoformat()
            buckets.setdefault(key, {"created": 0, "completed": 0, "overdue": 0})[label] = row[1]

    return {
        "range": {
            "start_at": effective_start.isoformat(),
            "end_at": effective_end.isoformat(),
        },
        "granularity": granularity,
        "items": [{"period": key, **values} for key, values in sorted(buckets.items())],
    }


def overdue_distribution(
    db: Session,
    principal: Principal,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    """超时工单按类别、部门、滞后时长分布；口径与超时标记一致。"""
    scope = require_permission(principal, "work_order", "read")
    conditions = _filters(
        start_at=start_at,
        end_at=end_at,
        category=None,
        department_id=None,
        assignee_id=None,
    )
    conditions.append(WorkOrder.is_overdue.is_(True))
    base = apply_work_order_scope(select(WorkOrder).where(*conditions), principal, scope)
    scoped = base.subquery()

    category_rows = db.execute(
        select(scoped.c.category, func.count()).group_by(scoped.c.category)
    ).all()
    department_rows = db.execute(
        select(scoped.c.department_id, func.count())
        .where(scoped.c.department_id.is_not(None))
        .group_by(scoped.c.department_id)
    ).all()

    now = datetime.now(UTC)
    aging = {"lte_8h": 0, "8h_24h": 0, "24h_72h": 0, "gt_72h": 0}
    due_rows = db.execute(select(scoped.c.due_at).where(scoped.c.due_at.is_not(None))).all()
    for (due_at,) in due_rows:
        hours = (now - due_at).total_seconds() / 3600
        if hours <= 8:
            aging["lte_8h"] += 1
        elif hours <= 24:
            aging["8h_24h"] += 1
        elif hours <= 72:
            aging["24h_72h"] += 1
        else:
            aging["gt_72h"] += 1

    return {
        "total": sum(row[1] for row in category_rows),
        "by_category": {row[0]: row[1] for row in category_rows},
        "by_department": {str(row[0]): row[1] for row in department_rows},
        "aging": aging,
    }
