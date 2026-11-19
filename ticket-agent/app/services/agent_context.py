"""Agent 操作上下文：让 service 层知道本次写操作来自 Agent 而非页面。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentContext:
    session_id: str
    agent_name: str = "work_order_agent"


_agent_context: ContextVar[AgentContext | None] = ContextVar("agent_context", default=None)


def set_agent_context(context: AgentContext | None) -> Token:
    return _agent_context.set(context)


def reset_agent_context(token: Token) -> None:
    try:
        _agent_context.reset(token)
    except ValueError:
        _agent_context.set(None)


def current_agent_context() -> AgentContext | None:
    return _agent_context.get()
