import ipaddress

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.core.rate_limit import check_login_rate_limit, clear_login_rate_limit
from app.models.report import ReportViewer
from app.schemas.auth import LoginIn, LogoutIn, RefreshIn
from app.services import auth_service
from app.services.permission_service import Principal

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """取客户端 IP；非合法 IP（如测试客户端标识）返回 None，避免写坏 inet 列。"""
    host = request.client.host if request.client else ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    check_login_rate_limit(ip or "")
    data = auth_service.login(
        db,
        employee_no=payload.employee_no,
        password=payload.password,
        ip=ip,
        request_id=getattr(request.state, "request_id", None),
    )
    clear_login_rate_limit(ip or "")
    return ok(request, data)


@router.post("/auth/refresh")
def refresh(payload: RefreshIn, request: Request, db: Session = Depends(get_db)):
    return ok(request, auth_service.refresh(db, refresh_token=payload.refresh_token))


@router.post("/auth/logout")
def logout(
    payload: LogoutIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    auth_service.logout(db, refresh_token=payload.refresh_token, user_id=principal.user_id)
    return ok(request, None)


@router.get("/users/me")
def me(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = auth_service.get_me(db, user_id=principal.user_id)
    data["permissions"] = [
        {
            "resource": p.resource,
            "action": p.action,
            "data_scope": p.data_scope,
            "business_domain": p.business_domain,
        }
        for p in principal.permissions
    ]
    data["report_viewer"] = (
        db.scalar(select(ReportViewer.id).where(ReportViewer.user_id == principal.user_id))
        is not None
    )
    return ok(request, data)
