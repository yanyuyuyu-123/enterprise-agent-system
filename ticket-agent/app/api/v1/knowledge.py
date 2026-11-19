"""知识库接口：上传、列表、详情、下载、删除、重处理与检索。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import knowledge_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=50)


@router.get("/documents")
def list_documents(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = knowledge_service.list_documents(
        db,
        principal,
        status=status,
        category=category,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/documents")
def upload_document(
    request: Request,
    title: str = Form(min_length=1, max_length=255),
    category: str = Form(default="other", max_length=32),
    visibility_scope: str = Form(default="department"),
    is_mock: bool = Form(default=False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = knowledge_service.upload_document(
        db,
        principal,
        file_name=file.filename or "unknown",
        data=file.file.read(),
        title=title,
        category=category,
        visibility_scope=visibility_scope,
        is_mock=is_mock,
    )
    return ok(request, data, status_code=201)


@router.get("/documents/{document_id}")
def get_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, knowledge_service.get_document(db, principal, document_id))


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, knowledge_service.delete_document(db, principal, document_id))


@router.post("/documents/{document_id}/reprocess")
def reprocess_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, knowledge_service.reprocess_document(db, principal, document_id))


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data, row = knowledge_service.download_document(db, principal, document_id)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{row.doc_no}.{row.file_ext}"; '
            f"filename*=UTF-8''{quote(row.file_name)}"
        )
    }
    return Response(content=data, media_type="application/octet-stream", headers=headers)


@router.post("/search")
def search(
    payload: SearchIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(
        request,
        knowledge_service.search(db, principal, payload.query, top_k=payload.top_k),
    )
