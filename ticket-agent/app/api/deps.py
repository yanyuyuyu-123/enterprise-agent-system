from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.models.org import User
from app.services.auth_service import is_revoked
from app.services.permission_service import (
    Principal,
    load_principal,
    require_permission,
)

_bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise AppError(2000, "未登录", 401)
    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise AppError(2000, "登录已失效，请重新登录", 401) from exc

    if payload.get("typ") != "access":
        raise AppError(2000, "令牌类型错误", 401)
    if is_revoked(payload["jti"]):
        raise AppError(2000, "登录已失效，请重新登录", 401)

    user = db.get(User, int(payload["sub"]))
    if user is None or user.deleted_at is not None:
        raise AppError(2000, "未登录", 401)
    if user.status != "active":
        raise AppError(2003, "账号已停用", 403)

    return load_principal(db, user)


def require(
    resource: str,
    action: str,
    *,
    scope: str | None = None,
) -> Callable[[Principal], Principal]:
    """依赖工厂：`Depends(require("work_order", "read", scope="department"))`。"""

    def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        require_permission(principal, resource, action, scope=scope)
        return principal

    return _dependency
