"""写操作二次确认令牌：Redis 存储、一次消费、参数与版本校验。"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.redis import redis_client
from app.services.flow_service import get_config_int
from app.services.permission_service import Principal

TOKEN_PREFIX = "agent:confirm:"
SESSION_PREFIX = "agent:confirm:sess:"


def _key(token: str) -> str:
    return f"{TOKEN_PREFIX}{token}"


def _session_key(user_id: int, session_id: str) -> str:
    return f"{SESSION_PREFIX}{user_id}:{session_id}"


def params_hash(params: dict[str, Any]) -> str:
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(
    db: Session,
    principal: Principal,
    *,
    action: str,
    params: dict[str, Any],
    summary: str,
    session_id: str,
    work_order_id: int | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    ttl = get_config_int(db, "agent.confirm.ttl_seconds", 300)
    token = f"c-{secrets.token_urlsafe(18)}"
    payload = {
        "user_id": principal.user_id,
        "action": action,
        "params": params,
        "params_hash": params_hash(params),
        "summary": summary,
        "work_order_id": work_order_id,
        "version": version,
        "session_id": session_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        redis_client.setex(_key(token), ttl, json.dumps(payload, ensure_ascii=False))
        redis_client.setex(_session_key(principal.user_id, session_id), ttl, token)
    except RedisError as exc:
        raise AppError(4000, "确认服务不可用，请稍后重试", 503) from exc

    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat()
    return {
        "type": "confirmation",
        "action": action,
        "summary": summary,
        "params": params,
        "confirm_token": token,
        "expires_at": expires_at,
    }


def load(token: str) -> dict[str, Any] | None:
    try:
        raw = redis_client.get(_key(token))
    except RedisError as exc:
        raise AppError(4000, "确认服务不可用，请稍后重试", 503) from exc
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def consume(token: str, *, user_id: int) -> dict[str, Any]:
    """取出并删除令牌；不存在、已过期或不是本人操作都视为失效。"""
    try:
        raw = redis_client.getdel(_key(token))
    except RedisError as exc:
        raise AppError(4000, "确认服务不可用，请稍后重试", 503) from exc
    if raw is None:
        raise AppError(3000, "确认已过期或已执行，请重新发起", 409)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(3000, "确认信息损坏，请重新发起", 409) from exc

    if int(data.get("user_id", 0)) != user_id:
        raise AppError(2004, "该确认不属于当前用户", 403)
    if params_hash(data.get("params") or {}) != data.get("params_hash"):
        raise AppError(3000, "确认参数不一致，请重新发起", 409)
    _clear_session(user_id, str(data.get("session_id") or ""))
    return data


def _clear_session(user_id: int, session_id: str) -> None:
    if not session_id:
        return
    try:
        redis_client.delete(_session_key(user_id, session_id))
    except RedisError:
        pass


def pending_for_session(user_id: int, session_id: str) -> str | None:
    """按会话取最近一次待确认令牌，供用户直接回复“确认”。"""
    try:
        raw = redis_client.get(_session_key(user_id, session_id))
    except RedisError:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw


def cancel(token: str, *, user_id: int) -> None:
    data = load(token)
    if data is None:
        raise AppError(3000, "确认已过期，无需取消", 409)
    if int(data.get("user_id", 0)) != user_id:
        raise AppError(2004, "该确认不属于当前用户", 403)
    try:
        redis_client.delete(_key(token))
        _clear_session(user_id, str(data.get("session_id") or ""))
    except RedisError as exc:
        raise AppError(4000, "确认服务不可用，请稍后重试", 503) from exc
