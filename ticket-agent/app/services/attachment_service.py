"""工单附件：上传、列表、下载。

V1 只支持本地存储；文件名一律重命名，原始文件名只入库展示。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    STATUS_SUPPLEMENTING,
)
from app.core.errors import AppError
from app.core.storage import get_storage
from app.models.work_order import WorkOrderAttachment
from app.services.flow_service import get_config_int
from app.services.permission_service import Principal
from app.services.work_order_service import visible_order

ALLOWED_MIME: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "doc": frozenset({"application/msword"}),
    "docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    "xls": frozenset({"application/vnd.ms-excel"}),
    "xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    "csv": frozenset({"text/csv", "application/csv", "text/plain"}),
    "txt": frozenset({"text/plain"}),
    "png": frozenset({"image/png"}),
    "jpg": frozenset({"image/jpeg"}),
    "jpeg": frozenset({"image/jpeg"}),
}

UPLOADABLE_STATUSES = (STATUS_SUPPLEMENTING, STATUS_PROCESSING, STATUS_PENDING_REVIEW)


def _validate_file(
    file_name: str, content_type: str | None, size: int, max_bytes: int
) -> tuple[str, str]:
    name = Path(file_name).name.strip()
    if not name or name.startswith(".") or name.count(".") != 1:
        raise AppError(1004, "文件名不合法：不允许多个扩展名", 400)

    ext = name.rsplit(".", 1)[1].lower()
    allowed = ALLOWED_MIME.get(ext)
    if allowed is None:
        raise AppError(1004, "不支持的文件类型", 400)

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared != "application/octet-stream" and declared not in allowed:
        raise AppError(1004, "文件类型与扩展名不符", 400)

    if size <= 0:
        raise AppError(1004, "文件内容为空", 400)
    if size > max_bytes:
        raise AppError(1004, f"文件超过 {max_bytes // (1024 * 1024)}MB 限制", 400)

    return name, ext


def _dict(row: WorkOrderAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "work_order_id": row.work_order_id,
        "file_name": row.file_name,
        "file_size": row.file_size,
        "mime_type": row.mime_type,
        "file_ext": row.file_ext,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "download_url": f"/api/v1/work_orders/{row.work_order_id}/attachments/{row.id}/download",
    }


def list_attachments(db: Session, principal: Principal, order_id: int) -> dict[str, Any]:
    visible_order(db, principal, order_id)
    rows = db.scalars(
        select(WorkOrderAttachment)
        .where(
            WorkOrderAttachment.work_order_id == order_id,
            WorkOrderAttachment.deleted_at.is_(None),
        )
        .order_by(WorkOrderAttachment.created_at, WorkOrderAttachment.id)
    ).all()
    return {"items": [_dict(row) for row in rows]}


def upload(
    db: Session,
    principal: Principal,
    order_id: int,
    *,
    file_name: str,
    content_type: str | None,
    data: bytes,
) -> dict[str, Any]:
    order = visible_order(db, principal, order_id)
    if order.status not in UPLOADABLE_STATUSES:
        raise AppError(3001, "当前状态不允许上传附件", 409)

    max_mb = get_config_int(db, "work_order.attachment.max_size_mb", 20)
    name, ext = _validate_file(file_name, content_type, len(data), max_mb * 1024 * 1024)

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    relative_path = f"work_orders/{order_id}/{stored_name}"
    storage = get_storage()
    storage.save(relative_path, data)

    row = WorkOrderAttachment(
        work_order_id=order_id,
        file_name=name,
        stored_name=stored_name,
        file_path=relative_path,
        file_size=len(data),
        mime_type=next(iter(ALLOWED_MIME[ext])),
        file_ext=ext,
        uploaded_by=principal.user_id,
    )
    try:
        db.add(row)
        db.commit()
    except Exception:
        storage.delete(relative_path)
        raise
    db.refresh(row)
    return _dict(row)


def download(
    db: Session, principal: Principal, order_id: int, attachment_id: int
) -> tuple[bytes, WorkOrderAttachment]:
    visible_order(db, principal, order_id)
    row = db.scalar(
        select(WorkOrderAttachment).where(
            WorkOrderAttachment.id == attachment_id,
            WorkOrderAttachment.work_order_id == order_id,
            WorkOrderAttachment.deleted_at.is_(None),
        )
    )
    if row is None:
        raise AppError(3003, "附件不存在", 404)
    return get_storage().read(row.file_path), row
