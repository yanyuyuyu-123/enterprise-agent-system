from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import notification_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    request: Request,
    is_read: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = notification_service.list_notifications(
        db, principal, is_read=is_read, page=page, page_size=page_size
    )
    return ok(request, data)


@router.post("/read-all")
def mark_all_read(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, notification_service.mark_all_read(db, principal))


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, notification_service.mark_read(db, principal, notification_id))
