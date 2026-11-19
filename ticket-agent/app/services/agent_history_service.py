"""Agent 会话历史：把每个会话的问答存档，供“历史会话”查看与恢复。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.misc import AgentMessage
from app.services.permission_service import Principal

TITLE_LIMIT = 30
PREVIEW_LIMIT = 60


def record_exchange(
    db: Session,
    principal: Principal,
    *,
    session_id: str,
    user_text: str,
    answer: str | None,
    sources: list[dict[str, Any]] | None = None,
    intent: str | None = None,
) -> None:
    sid = session_id[:64]
    db.add(
        AgentMessage(
            session_id=sid,
            user_id=principal.user_id,
            role="user",
            content=user_text[:20000],
        )
    )
    if answer:
        db.add(
            AgentMessage(
                session_id=sid,
                user_id=principal.user_id,
                role="assistant",
                content=answer[:20000],
                sources=sources or [],
                intent=intent[:64] if intent else None,
            )
        )
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("agent message write failed", extra={"session_id": sid})


def list_sessions(db: Session, principal: Principal, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 50))
    stmt = (
        select(
            AgentMessage.session_id,
            func.max(AgentMessage.created_at).label("last_at"),
            func.count().label("message_count"),
        )
        .where(AgentMessage.user_id == principal.user_id)
        .group_by(AgentMessage.session_id)
        .order_by(func.max(AgentMessage.created_at).desc())
        .limit(limit)
    )
    sessions: list[dict[str, Any]] = []
    for sid, last_at, message_count in db.execute(stmt).all():
        first = db.scalar(
            select(AgentMessage.content)
            .where(
                AgentMessage.user_id == principal.user_id,
                AgentMessage.session_id == sid,
                AgentMessage.role == "user",
            )
            .order_by(AgentMessage.id)
            .limit(1)
        )
        last = db.scalar(
            select(AgentMessage.content)
            .where(
                AgentMessage.user_id == principal.user_id,
                AgentMessage.session_id == sid,
            )
            .order_by(AgentMessage.id.desc())
            .limit(1)
        )
        title = " ".join((first or "未命名会话").split())[:TITLE_LIMIT]
        preview = " ".join((last or "").split())[:PREVIEW_LIMIT]
        sessions.append(
            {
                "session_id": sid,
                "title": title,
                "preview": preview,
                "message_count": message_count,
                "last_at": last_at.isoformat() if isinstance(last_at, datetime) else last_at,
            }
        )
    return sessions


def recent_messages(
    db: Session, principal: Principal, session_id: str, limit: int = 10
) -> list[dict[str, str]]:
    """取本会话最近的问答，作为改写、意图识别和领域追问的上下文。"""
    rows = db.scalars(
        select(AgentMessage)
        .where(
            AgentMessage.user_id == principal.user_id,
            AgentMessage.session_id == session_id,
        )
        .order_by(AgentMessage.id.desc())
        .limit(max(1, limit))
    ).all()
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]


def session_messages(db: Session, principal: Principal, session_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AgentMessage)
        .where(
            AgentMessage.user_id == principal.user_id,
            AgentMessage.session_id == session_id,
        )
        .order_by(AgentMessage.id)
    ).all()
    return [
        {
            "role": row.role,
            "content": row.content,
            "sources": row.sources or [],
            "intent": row.intent,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
