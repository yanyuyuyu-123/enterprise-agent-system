"""V3 报告接口：列表、详情、下载与查看名单维护。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import report_service
from app.services.permission_service import Principal

router = APIRouter(tags=["report"])


class ViewerIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=200)


@router.get("/reports")
def list_reports(
    request: Request,
    report_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = report_service.list_reports(
        db,
        principal,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.get("/reports/{report_id}")
def get_report(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, report_service.get_report(db, principal, report_id))


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    report, content = report_service.get_report_file(db, principal, report_id)
    return Response(
        content=content,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{report.report_no}.html"',
        },
    )


@router.get("/report-viewers/candidates")
def list_viewer_candidates(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, report_service.list_viewer_candidates(db, principal))


@router.get("/report-viewers")
def list_viewers(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, report_service.list_viewers(db, principal))


@router.put("/report-viewers")
def update_viewers(
    request: Request,
    payload: ViewerIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, report_service.update_viewers(db, principal, payload.user_ids))
