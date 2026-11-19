"""知识库工具：只做检索，引用带文档与位置。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services import knowledge_service
from app.services.permission_service import Principal


def tool_search(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    top_k = args.get("top_k")
    result = knowledge_service.search(
        db, principal, query, top_k=int(top_k) if top_k is not None else None
    )
    return {
        "ok": result["found"],
        "data": result,
        "source": {"type": "knowledge_document", "query": query},
        "message": result["message"] or "ok",
    }
