from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.core.errors import AppError
from app.services import agent_history_service, agent_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/agent", tags=["agent"])

TOKEN_CHUNK = 40


class ChatIn(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=2000)
    confirm_token: str | None = Field(default=None, max_length=64)
    cancel: bool = False


def _events(data: dict[str, Any]) -> list[dict[str, Any]]:
    answer = data.get("answer") or ""
    events: list[dict[str, Any]] = [
        {
            "type": "start",
            "session_id": data.get("session_id"),
            "intent": data.get("intent"),
        }
    ]
    for offset in range(0, len(answer), TOKEN_CHUNK):
        events.append({"type": "token", "content": answer[offset : offset + TOKEN_CHUNK]})
    events.append({"type": "result", **data})
    return events


def _stream(events: list[dict[str, Any]]):
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.get("/sessions")
def list_sessions(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, agent_history_service.list_sessions(db, principal, limit))


@router.get("/sessions/{session_id}/messages")
def session_messages(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(
        request,
        {
            "session_id": session_id,
            "messages": agent_history_service.session_messages(db, principal, session_id),
        },
    )


@router.post("/chat")
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        data = agent_service.chat(
            db,
            principal,
            message=payload.message,
            session_id=payload.session_id,
            confirm_token=payload.confirm_token,
            cancel=payload.cancel,
        )
        events = _events(data)
    except AppError as exc:
        events = [{"type": "error", "code": exc.code, "message": exc.message}]

    return StreamingResponse(
        _stream(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
