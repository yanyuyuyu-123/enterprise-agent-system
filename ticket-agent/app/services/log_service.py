from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    SCOPE_DEPARTMENT,
    SCOPE_SELF,
    SCOPE_SELF_AND_SUBORDINATES,
)
from app.core.crypto import encrypt_text
from app.core.errors import AppError
from app.core.logging import logger
from app.models.misc import AgentLog, OperationLog
from app.models.org import User
from app.services.permission_service import Principal, require_permission

# 敏感字段：只进加密列，不进可检索的 detail
SENSITIVE_KEYS = frozenset(
    {"password", "phone", "id_card", "bank_account", "salary", "amount", "token"}
)

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def current_request_id() -> str | None:
    return _request_id.get()


def write_log(
    db: Session,
    *,
    resource: str,
    action: str,
    log_type: str = "operation",
    user_id: int | None = None,
    user_name: str | None = None,
    department_id: int | None = None,
    log_level: str = "normal",
    target_type: str | None = None,
    target_id: str | int | None = None,
    result: str = "success",
    request_id: str | None = None,
    ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """只增日志；敏感键加密进 sensitive_detail，不出现在 detail。"""
    detail = detail or {}
    sensitive = {k: v for k, v in detail.items() if k in SENSITIVE_KEYS}
    safe_detail = {k: v for k, v in detail.items() if k not in SENSITIVE_KEYS}
    request_id = request_id or current_request_id()

    encrypted: bytes | None = None
    if sensitive:
        import json

        encrypted = encrypt_text(json.dumps(sensitive, ensure_ascii=False, default=str))

    db.add(
        OperationLog(
            log_type=log_type,
            log_level=log_level,
            user_id=user_id,
            user_name_snapshot=user_name,
            department_id=department_id,
            resource=resource,
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            result=result,
            request_id=request_id,
            ip=ip,
            detail=safe_detail,
            sensitive_detail=encrypted,
        )
    )


def write_log_safely(db: Session, **kwargs: Any) -> None:
    """日志失败不影响主流程，仅告警。"""
    try:
        write_log(db, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("write operation log failed")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _log_dict(row: OperationLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "log_type": row.log_type,
        "log_level": row.log_level,
        "user_id": row.user_id,
        "user_name": row.user_name_snapshot,
        "department_id": row.department_id,
        "resource": row.resource,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "result": row.result,
        "detail": row.detail,
        "has_sensitive": row.sensitive_detail is not None,
        "request_id": row.request_id,
        "created_at": _iso(row.created_at),
    }


def _subordinate_ids(principal: Principal):
    return select(User.id).where(
        User.manager_id == principal.user_id,
        User.deleted_at.is_(None),
    )


def query_logs(
    db: Session,
    principal: Principal,
    *,
    log_type: str,
    permission_resource: str,
    log_level: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    target_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """按数据范围查询日志；sensitive_detail 一律不返回。"""
    scope = require_permission(principal, permission_resource, "read")
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)

    stmt = select(OperationLog).where(OperationLog.log_type == log_type)
    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        stmt = stmt.where(OperationLog.department_id == principal.department_id)
    elif scope == SCOPE_SELF:
        stmt = stmt.where(OperationLog.user_id == principal.user_id)
    elif scope == SCOPE_SELF_AND_SUBORDINATES:
        stmt = stmt.where(
            or_(
                OperationLog.user_id == principal.user_id,
                OperationLog.user_id.in_(_subordinate_ids(principal)),
            )
        )

    if log_level:
        stmt = stmt.where(OperationLog.log_level == log_level)
    if action:
        stmt = stmt.where(OperationLog.action == action)
    if resource:
        stmt = stmt.where(OperationLog.resource == resource)
    if result:
        stmt = stmt.where(OperationLog.result == result)
    if target_id:
        stmt = stmt.where(OperationLog.target_id == target_id)
    if start_at:
        stmt = stmt.where(OperationLog.created_at >= start_at)
    if end_at:
        stmt = stmt.where(OperationLog.created_at <= end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_log_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def query_agent_logs(
    db: Session,
    principal: Principal,
    *,
    session_id: str | None = None,
    tool_name: str | None = None,
    success: bool | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Agent 调用记录；按操作日志权限与数据范围过滤。"""
    scope = require_permission(principal, "operation_log", "read")
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)

    stmt = select(AgentLog)
    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        stmt = stmt.where(
            AgentLog.user_id.in_(
                select(User.id).where(
                    User.department_id == principal.department_id,
                    User.deleted_at.is_(None),
                )
            )
        )
    elif scope == SCOPE_SELF:
        stmt = stmt.where(AgentLog.user_id == principal.user_id)
    elif scope == SCOPE_SELF_AND_SUBORDINATES:
        stmt = stmt.where(
            or_(
                AgentLog.user_id == principal.user_id,
                AgentLog.user_id.in_(_subordinate_ids(principal)),
            )
        )

    if session_id:
        stmt = stmt.where(AgentLog.session_id == session_id)
    if tool_name:
        stmt = stmt.where(AgentLog.tool_name == tool_name)
    if success is not None:
        stmt = stmt.where(AgentLog.success.is_(success))
    if start_at:
        stmt = stmt.where(AgentLog.created_at >= start_at)
    if end_at:
        stmt = stmt.where(AgentLog.created_at <= end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AgentLog.created_at.desc(), AgentLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "user_id": row.user_id,
                "agent_name": row.agent_name,
                "intent": row.intent,
                "tool_name": row.tool_name,
                "input_summary": row.input_summary,
                "output_summary": row.output_summary,
                "success": row.success,
                "error_code": row.error_code,
                "latency_ms": row.latency_ms,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
