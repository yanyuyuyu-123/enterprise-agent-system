from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import log_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/operation")
def operation_logs(
    request: Request,
    log_level: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    target_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = log_service.query_logs(
        db,
        principal,
        log_type="operation",
        permission_resource="operation_log",
        log_level=log_level,
        action=action,
        resource=resource,
        result=result,
        target_id=target_id,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.get("/agent")
def agent_logs(
    request: Request,
    session_id: str | None = None,
    tool_name: str | None = None,
    success: bool | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = log_service.query_agent_logs(
        db,
        principal,
        session_id=session_id,
        tool_name=tool_name,
        success=success,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.get("/system")
def system_logs(
    request: Request,
    log_level: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    target_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = log_service.query_logs(
        db,
        principal,
        log_type="system",
        permission_resource="system_log",
        log_level=log_level,
        action=action,
        resource=resource,
        result=result,
        target_id=target_id,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)
