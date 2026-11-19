"""知识库查询 Agent：只做文档检索与引用，不查实时业务数据。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services import knowledge_service
from app.services.permission_service import Principal

LIST_KEYWORDS = (
    "文档有哪些",
    "有哪些文档",
    "文档列表",
    "有哪些资料",
    "哪些文档",
    "多少个文档",
    "有什么文件",
    "有哪些文件",
    "文件有哪些",
    "文件列表",
    "哪些文件",
    "有什么资料",
    "有什么文档",
    "知识库里有什么",
    "知识库有什么",
)
STATUS_LABELS = {
    "ready": "已就绪",
    "pending": "解析中",
    "failed": "解析失败",
    "need_ocr": "待 OCR",
}


def _list_documents(db: Session, principal: Principal, question: str) -> dict[str, Any] | None:
    """问"有哪些文档"时直接列清单，语义检索答不了这类问题。"""
    if not any(word in question for word in LIST_KEYWORDS):
        return None
    data = knowledge_service.list_documents(db, principal, page=1, page_size=10)
    items = data.get("items") or []
    if not items:
        return {
            "status": "ok",
            "answer": "企业知识库里还没有文档，可以先在知识库页面上传。",
            "sources": [],
            "missing": [],
        }
    total = data.get("total", len(items))
    if total > len(items):
        lines = [f"共 {total} 份文档，先列出最近 {len(items)} 份："]
    else:
        lines = [f"共 {total} 份文档："]
    for item in items:
        status = STATUS_LABELS.get(item["status"], item["status"])
        lines.append(f"· {item['title']}（{item['file_name']}，{status}）")
    return {"status": "ok", "answer": "\n".join(lines), "sources": [], "missing": []}


def run(
    db: Session, principal: Principal, question: str, *, top_k: int | None = None
) -> dict[str, Any]:
    try:
        listed = _list_documents(db, principal, question)
    except AppError as exc:
        return {
            "status": "failed",
            "answer": exc.message,
            "sources": [],
            "missing": ["知识库文档列表"],
        }
    if listed is not None:
        return listed

    try:
        result = knowledge_service.search(db, principal, question, top_k=top_k)
    except AppError as exc:
        return {
            "status": "failed",
            "answer": exc.message,
            "sources": [],
            "missing": ["知识库检索"],
        }

    # 同一份文档可能命中多个段落，回答和引用都按文档合并，避免重复刷屏
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in result["items"]:
        key = str(item["document_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    sources = [
        {
            "type": "knowledge_document",
            "id": str(item["document_id"]),
            "title": item["title"],
            "locator": item["locator"],
            "file_name": item["file_name"],
        }
        for item in unique[:5]
    ]
    if not sources:
        return {
            "status": "ok",
            "answer": result["message"],
            "sources": [],
            "missing": [],
        }
    lines = [
        f"《{item['title']}》{item['locator']}：{item['content'][:600]}" for item in unique[:3]
    ]
    return {"status": "ok", "answer": "\n".join(lines), "sources": sources, "missing": []}
