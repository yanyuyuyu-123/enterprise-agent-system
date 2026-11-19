from __future__ import annotations

from datetime import UTC, datetime

from jwt import InvalidTokenError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import logger
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.org import Position, User, UserPosition
from app.services.log_service import write_log_safely

BLACKLIST_PREFIX = "jwt:blacklist:"


def _revoke(payload: dict) -> None:
    ttl = int(payload.get("exp", 0)) - int(datetime.now(UTC).timestamp())
    if ttl <= 0:
        return
    try:
        redis_client.setex(f"{BLACKLIST_PREFIX}{payload['jti']}", ttl, "1")
    except RedisError:
        logger.warning("redis unavailable, token not revoked")


def is_revoked(jti: str) -> bool:
    try:
        return redis_client.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
    except RedisError:
        logger.warning("redis unavailable, skip blacklist check")
        return False


def _position_codes(db: Session, user_id: int) -> list[str]:
    rows = db.scalars(
        select(Position.code)
        .join(UserPosition, UserPosition.position_id == Position.id)
        .where(
            UserPosition.user_id == user_id,
            UserPosition.deleted_at.is_(None),
            Position.deleted_at.is_(None),
            Position.is_active.is_(True),
        )
    ).all()
    return list(rows)


def _issue_tokens(user: User, positions: list[str]) -> dict:
    return {
        "access_token": create_access_token(user.id, positions),
        "refresh_token": create_refresh_token(user.id, positions),
        "token_type": "bearer",
    }


def login(
    db: Session,
    *,
    employee_no: str,
    password: str,
    ip: str | None,
    request_id: str | None,
) -> dict:
    user = db.scalar(
        select(User).where(
            User.employee_no == employee_no,
            User.deleted_at.is_(None),
        )
    )
    # 不区分"用户不存在"与"密码错误"
    if user is None or not verify_password(password, user.password_hash):
        write_log_safely(
            db,
            resource="auth",
            action="login",
            user_name=employee_no,
            result="failure",
            request_id=request_id,
            ip=ip,
            detail={"reason": "bad_credentials"},
        )
        db.commit()
        raise AppError(2000, "工号或密码错误", 401)

    if user.status != "active":
        write_log_safely(
            db,
            resource="auth",
            action="login",
            user_id=user.id,
            user_name=user.name,
            department_id=user.department_id,
            result="denied",
            request_id=request_id,
            ip=ip,
            detail={"reason": "disabled"},
        )
        db.commit()
        raise AppError(2003, "账号已停用", 403)

    user.last_login_at = datetime.now(UTC)
    positions = _position_codes(db, user.id)
    tokens = _issue_tokens(user, positions)

    write_log_safely(
        db,
        resource="auth",
        action="login",
        user_id=user.id,
        user_name=user.name,
        department_id=user.department_id,
        request_id=request_id,
        ip=ip,
    )
    db.commit()
    return tokens


def refresh(db: Session, *, refresh_token: str) -> dict:
    payload = _decode(refresh_token, expected_type="refresh")
    if is_revoked(payload["jti"]):
        raise AppError(2000, "登录已失效，请重新登录", 401)

    user = _active_user(db, payload["sub"])
    _revoke(payload)  # 轮换：旧 refresh 立即失效
    return _issue_tokens(user, _position_codes(db, user.id))


def logout(db: Session, *, refresh_token: str, user_id: int | None = None) -> None:
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError:
        return
    _revoke(payload)
    write_log_safely(
        db,
        resource="auth",
        action="logout",
        user_id=user_id,
        request_id=None,
    )
    db.commit()


def _decode(token: str, *, expected_type: str) -> dict:
    try:
        payload = decode_token(token)
    except InvalidTokenError as exc:
        raise AppError(2000, "登录已失效，请重新登录", 401) from exc
    if payload.get("typ") != expected_type:
        raise AppError(2000, "令牌类型错误", 401)
    return payload


def _active_user(db: Session, subject: str) -> User:
    user = db.get(User, int(subject))
    if user is None or user.deleted_at is not None:
        raise AppError(2000, "登录已失效，请重新登录", 401)
    if user.status != "active":
        raise AppError(2003, "账号已停用", 403)
    return user


def get_me(db: Session, *, user_id: int) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(2000, "未登录", 401)

    rows = db.execute(
        select(
            Position.code,
            Position.name,
            Position.data_scope,
            Position.business_domain,
        )
        .join(UserPosition, UserPosition.position_id == Position.id)
        .where(
            UserPosition.user_id == user_id,
            UserPosition.deleted_at.is_(None),
            Position.deleted_at.is_(None),
            Position.is_active.is_(True),
        )
    ).all()

    return {
        "id": user.id,
        "employee_no": user.employee_no,
        "name": user.name,
        "department_id": user.department_id,
        "positions": [
            {
                "code": row.code,
                "name": row.name,
                "data_scope": row.data_scope,
                "business_domain": row.business_domain,
            }
            for row in rows
        ],
    }
