from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import attachment_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/work_orders", tags=["attachments"])


@router.post("/{order_id}/attachments")
async def upload_attachment(
    order_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = await file.read()
    meta = attachment_service.upload(
        db,
        principal,
        order_id,
        file_name=file.filename or "",
        content_type=file.content_type,
        data=data,
    )
    return ok(request, meta, status_code=201)


@router.get("/{order_id}/attachments")
def list_attachments(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, attachment_service.list_attachments(db, principal, order_id))


@router.get("/{order_id}/attachments/{attachment_id}/download")
def download_attachment(
    order_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data, row = attachment_service.download(db, principal, order_id, attachment_id)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{row.stored_name}"; ' f"filename*=UTF-8''{quote(row.file_name)}"
        )
    }
    return Response(content=data, media_type=row.mime_type, headers=headers)
