"""按岗位取通知接收人：报告、预警共用，只读组织数据。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import Position, User, UserPosition


def user_ids_by_positions(db: Session, *position_codes: str) -> list[int]:
    """取在岗、在职且岗位命中的用户 id，去重。"""
    if not position_codes:
        return []
    rows = db.scalars(
        select(User.id)
        .join(UserPosition, UserPosition.user_id == User.id)
        .join(Position, Position.id == UserPosition.position_id)
        .where(
            Position.code.in_(position_codes),
            Position.is_active.is_(True),
            Position.deleted_at.is_(None),
            UserPosition.deleted_at.is_(None),
            User.status == "active",
            User.deleted_at.is_(None),
        )
    ).all()
    return sorted(set(rows))
