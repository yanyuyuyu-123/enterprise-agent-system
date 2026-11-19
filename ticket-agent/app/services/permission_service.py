from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import SCOPE_BUSINESS_DOMAIN, SCOPE_ORDER
from app.core.errors import AppError
from app.models.org import Position, PositionPermission, User, UserPosition


@dataclass(frozen=True, slots=True)
class Permission:
    resource: str
    action: str
    data_scope: str
    business_domain: str | None = None


@dataclass(frozen=True, slots=True)
class Principal:
    """一次请求的身份快照：用户、岗位、权限并集。"""

    user_id: int
    employee_no: str
    name: str
    department_id: int | None
    position_codes: frozenset[str]
    permissions: tuple[Permission, ...]

    def has_position(self, *codes: str) -> bool:
        return bool(self.position_codes.intersection(codes))


def load_principal(db: Session, user: User) -> Principal:
    rows = db.execute(
        select(
            Position.code,
            PositionPermission.resource,
            PositionPermission.action,
            PositionPermission.data_scope,
            PositionPermission.business_domain,
        )
        .join(UserPosition, UserPosition.position_id == Position.id)
        .outerjoin(
            PositionPermission,
            (PositionPermission.position_id == Position.id)
            & (PositionPermission.is_allowed.is_(True)),
        )
        .where(
            UserPosition.user_id == user.id,
            UserPosition.deleted_at.is_(None),
            Position.deleted_at.is_(None),
            Position.is_active.is_(True),
        )
    ).all()

    codes = frozenset(row.code for row in rows)
    permissions = tuple(
        Permission(row.resource, row.action, row.data_scope, row.business_domain)
        for row in rows
        if row.resource is not None
    )
    return Principal(
        user_id=user.id,
        employee_no=user.employee_no,
        name=user.name,
        department_id=user.department_id,
        position_codes=codes,
        permissions=permissions,
    )


def require_permission(
    principal: Principal,
    resource: str,
    action: str,
    *,
    scope: str | None = None,
) -> str:
    """返回命中的 data_scope；无权限抛 2001，范围不足抛 2002。

    多岗位取并集、多条取最大范围。业务域授权（business_domain）不参与
    通用范围比较，仅对该资源本身生效。
    """
    hits = [p for p in principal.permissions if p.resource == resource and p.action == action]
    if not hits:
        raise AppError(2001, "无该资源权限", 403)

    general_hits = [p for p in hits if p.data_scope != SCOPE_BUSINESS_DOMAIN]

    if not general_hits:
        # 只有业务域授权：该资源按业务域全量可见，不再比较通用范围
        return SCOPE_BUSINESS_DOMAIN

    best = max(general_hits, key=lambda p: SCOPE_ORDER.get(p.data_scope, 0))
    if scope is not None and SCOPE_ORDER.get(best.data_scope, 0) < SCOPE_ORDER.get(scope, 0):
        raise AppError(2002, "超出数据范围", 403)
    return best.data_scope


def has_permission(principal: Principal, resource: str, action: str) -> bool:
    return any(p.resource == resource and p.action == action for p in principal.permissions)
