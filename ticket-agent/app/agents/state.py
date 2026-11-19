from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """V1 工单 Agent 的状态；所有值必须可 JSON 序列化，供 checkpointer 持久化。"""

    session_id: str
    original_text: str
    rewritten_text: str
    intent: str
    entities: dict[str, Any]
    tool_name: str | None
    tool_args: dict[str, Any]
    tool_result: dict[str, Any] | None
    confirmation: dict[str, Any] | None
    needs_clarification: bool
    clarification: str | None
    answer: str
    source: dict[str, Any]
    error: str | None
    history: list[dict[str, str]]
    llm_calls: list[dict[str, Any]]
