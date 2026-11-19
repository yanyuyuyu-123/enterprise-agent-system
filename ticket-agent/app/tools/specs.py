from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.permission_service import Principal


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: tuple[str, str]
    is_write: bool
    handler: Callable[[Session, Principal, dict[str, Any]], dict[str, Any]]
    timeout_s: float = 5.0
    max_retries: int = 1


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["ok", "data", "source", "message"],
    "properties": {
        "ok": {"type": "boolean"},
        "data": {},
        "source": {"type": "object"},
        "message": {"type": "string"},
    },
}
