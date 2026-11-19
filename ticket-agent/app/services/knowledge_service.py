"""知识文档：上传、列表、下载、删除、重处理与检索。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import KNOWLEDGE_CATEGORIES
from app.core.errors import AppError
from app.core.logging import logger
from app.core.storage import get_storage
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag import embedder
from app.rag.parser import LEGACY_EXTENSIONS, SUPPORTED_EXTENSIONS
from app.services import ingest_service
from app.services.log_service import write_log_safely
from app.services.mock_service import ensure_mock_writable
from app.services.permission_service import Principal, require_permission
from app.services.setting_service import get_float, get_int

COMPANY_SCOPE_POSITIONS = ("hr_specialist", "hr_head", "general_manager")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _payload(row: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "doc_no": row.doc_no,
        "title": row.title,
        "category": row.category,
        "file_name": row.file_name,
        "file_ext": row.file_ext,
        "file_size": row.file_size,
        "visibility_scope": row.visibility_scope,
        "department_id": row.department_id,
        "owner_id": row.owner_id,
        "status": row.status,
        "version": row.version,
        "embedding_model": row.embedding_model,
        "chunk_count": row.chunk_count,
        "error_message": row.error_message,
        "parsed_at": _iso(row.parsed_at),
        "is_mock": row.is_mock,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _visible(principal: Principal):
    if principal.department_id is None:
        return KnowledgeDocument.visibility_scope == "company"
    return or_(
        KnowledgeDocument.visibility_scope == "company",
        KnowledgeDocument.department_id == principal.department_id,
    )


def _load(db: Session, principal: Principal, document_id: int) -> KnowledgeDocument:
    row = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.deleted_at.is_(None),
            _visible(principal),
        )
    )
    if row is None:
        raise AppError(3003, "文档不存在或不可见", 404)
    return row


def list_documents(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "read")
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.deleted_at.is_(None), _visible(principal)
    )
    if status:
        stmt = stmt.where(KnowledgeDocument.status == status)
    if category:
        stmt = stmt.where(KnowledgeDocument.category == category)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(KnowledgeDocument.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_document(db: Session, principal: Principal, document_id: int) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "read")
    return _payload(_load(db, principal, document_id))


def upload_document(
    db: Session,
    principal: Principal,
    *,
    file_name: str,
    data: bytes,
    title: str,
    category: str,
    visibility_scope: str,
    is_mock: bool,
) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "create")
    ensure_mock_writable(is_mock)
    embedder.ensure_configured()

    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext in LEGACY_EXTENSIONS:
        raise AppError(1004, "旧格式无法解析，请另存为 docx/xlsx", 400)
    if ext not in SUPPORTED_EXTENSIONS:
        raise AppError(1004, "不支持的文件类型", 400)
    if not data:
        raise AppError(1004, "文件为空", 400)
    max_mb = get_int(db, "knowledge.document.max_size_mb", 50)
    if len(data) > max_mb * 1024 * 1024:
        raise AppError(1004, f"文件超过 {max_mb}MB 限制", 400)
    if visibility_scope not in ("company", "department"):
        raise AppError(1000, "可见范围不合法", 400)
    category = (category or "other").strip()
    if category not in KNOWLEDGE_CATEGORIES:
        raise AppError(1000, "文档分类不合法", 400)
    if visibility_scope == "company" and not principal.has_position(*COMPANY_SCOPE_POSITIONS):
        raise AppError(2001, "当前岗位只能创建部门文档", 403)
    if visibility_scope == "department" and principal.department_id is None:
        raise AppError(3000, "账号未分配部门，无法上传部门文档", 403)

    document = KnowledgeDocument(
        doc_no=f"KD{datetime.now(UTC):%Y%m%d}{uuid4().hex[:8].upper()}",
        title=title.strip(),
        category=category,
        file_name=file_name,
        file_path="",
        file_ext=ext,
        file_size=len(data),
        file_hash=hashlib.sha256(data).hexdigest(),
        department_id=principal.department_id,
        visibility_scope=visibility_scope,
        owner_id=principal.user_id,
        status="pending",
        version=1,
        is_mock=is_mock,
    )
    db.add(document)
    db.flush()

    relative_path = f"knowledge/{document.id}/{uuid4().hex}.{ext}"
    get_storage().save(relative_path, data)
    document.file_path = relative_path

    write_log_safely(
        db,
        resource="knowledge_document",
        action="upload",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="normal",
        target_type="knowledge_document",
        target_id=document.doc_no,
        detail={"file_ext": ext, "file_size": len(data), "is_mock": is_mock},
    )
    db.commit()

    try:
        ingest_service.enqueue_parse(document.id, document.version)
    except Exception as exc:  # noqa: BLE001 - 队列不可用时保留 pending，可通过重处理恢复
        logger.warning(
            "enqueue parse failed",
            extra={"document_id": document.id, "error": str(exc)},
        )
    db.refresh(document)
    return _payload(document)


def download_document(
    db: Session, principal: Principal, document_id: int
) -> tuple[bytes, KnowledgeDocument]:
    require_permission(principal, "knowledge_document", "read")
    row = _load(db, principal, document_id)
    return get_storage().read(row.file_path), row


def delete_document(db: Session, principal: Principal, document_id: int) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "delete")
    row = _load(db, principal, document_id)
    row.deleted_at = datetime.now(UTC)
    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == row.id))
    row.chunk_count = 0
    write_log_safely(
        db,
        resource="knowledge_document",
        action="delete",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="knowledge_document",
        target_id=row.doc_no,
        detail={"title": row.title, "is_mock": row.is_mock},
    )
    db.commit()
    return _payload(row)


def reprocess_document(db: Session, principal: Principal, document_id: int) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "update")
    embedder.ensure_configured()
    row = _load(db, principal, document_id)
    if row.status == "parsing":
        raise AppError(3001, "文档正在解析中", 409)
    row.version += 1
    row.status = "pending"
    row.error_message = None
    write_log_safely(
        db,
        resource="knowledge_document",
        action="reprocess",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="normal",
        target_type="knowledge_document",
        target_id=row.doc_no,
        detail={"version": row.version},
    )
    db.commit()
    try:
        ingest_service.enqueue_parse(row.id, row.version)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "enqueue reprocess failed",
            extra={"document_id": row.id, "error": str(exc)},
        )
    db.refresh(row)
    return _payload(row)


def _locator(chunk: KnowledgeChunk) -> str:
    if chunk.page_no is not None:
        return f"第 {chunk.page_no} 页"
    if chunk.sheet_name is not None and chunk.row_no is not None:
        return f"工作表“{chunk.sheet_name}”第 {chunk.row_no} 行"
    if chunk.row_no is not None:
        return f"第 {chunk.row_no} 行"
    if chunk.paragraph_no is not None:
        return f"第 {chunk.paragraph_no} 段"
    return ""


def search(
    db: Session,
    principal: Principal,
    query: str,
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
    require_permission(principal, "knowledge_document", "read")
    embedder.ensure_configured()
    text = query.strip()
    if not text:
        raise AppError(1001, "检索内容不能为空", 400)

    limit = top_k or get_int(db, "knowledge.retrieval.top_k", 8)
    min_score = get_float(db, "knowledge.retrieval.min_score", 0.25)
    vector = embedder.embed_texts([text], get_int(db, "embedding.batch_size", 16))[0]
    distance = KnowledgeChunk.embedding.cosine_distance(vector).label("distance")
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument, distance)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeDocument.status == "ready",
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeChunk.embedding.is_not(None),
            _visible(principal),
            distance <= 1 - min_score,
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    items = [
        {
            "document_id": document.id,
            "title": document.title,
            "file_name": document.file_name,
            "chunk_id": chunk.id,
            "content": chunk.content,
            "score": round(1 - float(score_distance), 4),
            "locator": _locator(chunk),
            "page_no": chunk.page_no,
            "sheet_name": chunk.sheet_name,
            "row_no": chunk.row_no,
            "paragraph_no": chunk.paragraph_no,
        }
        for chunk, document, score_distance in rows
    ]
    return {
        "query": text,
        "found": bool(items),
        "items": items,
        "message": None if items else "未在企业文档中找到依据",
        "min_score": min_score,
    }
