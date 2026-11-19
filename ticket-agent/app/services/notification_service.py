"""站内通知：写入与查询。通知内容不含金额等敏感字段。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.misc import Notification
from app.models.org import PositionPermission, User, UserPosition
from app.services.permission_service import Principal


def notify(
    db: Session,
    *,
    user_id: int | None,
    type: str,
    title: str,
    content: str,
    related_id: int | None = None,
    related_type: str = "work_order",
) -> None:
    """写一条站内通知；接收人不存在时忽略。"""
    if user_id is None:
        return
    db.add(
        Notification(
            user_id=user_id,
            type=type,
            title=title[:128],
            content=content[:1000],
            related_type=related_type if related_id is not None else None,
            related_id=related_id,
        )
    )


def notify_permission_holders(
    db: Session,
    *,
    resource: str,
    action: str,
    type: str,
    title: str,
    content: str,
    related_id: int | None = None,
    related_type: str = "stock_movement",
    exclude_user_id: int | None = None,
    department_id: int | None = None,
) -> None:
    """给拥有指定权限的启用用户发站内通知；可按部门过滤数据范围。"""
    stmt = (
        select(User.id)
        .join(UserPosition, UserPosition.user_id == User.id)
        .join(PositionPermission, PositionPermission.position_id == UserPosition.position_id)
        .where(
            PositionPermission.resource == resource,
            PositionPermission.action == action,
            PositionPermission.is_allowed.is_(True),
            User.status == "active",
            User.deleted_at.is_(None),
            UserPosition.deleted_at.is_(None),
        )
        .distinct()
    )
    if department_id is not None:
        # company 看全部；business_domain 是跨部门的业务域角色（如仓库负责人），也要通知；
        # department 只看本部门单据。
        stmt = stmt.where(
            or_(
                PositionPermission.data_scope.in_(("company", "business_domain")),
                User.department_id == department_id,
            )
        )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    for user_id in db.scalars(stmt).all():
        notify(
            db,
            user_id=user_id,
            type=type,
            title=title,
            content=content,
            related_id=related_id,
            related_type=related_type,
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dict(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "content": row.content,
        "related_type": row.related_type,
        "related_id": row.related_id,
        "is_read": row.is_read,
        "read_at": _iso(row.read_at),
        "created_at": _iso(row.created_at),
    }


def list_notifications(
    db: Session,
    principal: Principal,
    *,
    is_read: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)

    conditions = [Notification.user_id == principal.user_id]
    if is_read is not None:
        conditions.append(Notification.is_read.is_(is_read))

    total = db.scalar(select(func.count(Notification.id)).where(*conditions)) or 0
    unread = (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == principal.user_id,
                Notification.is_read.is_(False),
            )
        )
        or 0
    )
    rows = db.scalars(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_dict(row) for row in rows],
        "total": total,
        "unread": unread,
        "page": page,
        "page_size": page_size,
    }


def mark_read(db: Session, principal: Principal, notification_id: int) -> dict[str, Any]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == principal.user_id,
        )
    )
    if row is None:
        raise AppError(3003, "通知不存在", 404)
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(UTC)
        db.commit()
    return _dict(row)


def mark_all_read(db: Session, principal: Principal) -> dict[str, Any]:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == principal.user_id,
            Notification.is_read.is_(False),
        )
    ).all()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return {"updated": len(rows)}
