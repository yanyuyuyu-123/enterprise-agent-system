from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import stats_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/work_orders")
def work_order_stats(
    request: Request,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    category: str | None = None,
    department_id: int | None = None,
    assignee_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = stats_service.work_order_stats(
        db,
        principal,
        start_at=start_at,
        end_at=end_at,
        category=category,
        department_id=department_id,
        assignee_id=assignee_id,
    )
    return ok(request, data)


@router.get("/work-orders/trend")
def work_order_trend(
    request: Request,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    granularity: str = "day",
    category: str | None = None,
    department_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = stats_service.work_order_trend(
        db,
        principal,
        start_at=start_at,
        end_at=end_at,
        granularity=granularity,
        category=category,
        department_id=department_id,
    )
    return ok(request, data)


@router.get("/finance-trend")
def finance_trend(
    request: Request,
    months: int = 6,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = stats_service.finance_trend(db, principal, months=months)
    return ok(request, data)


@router.get("/work-orders/overdue-distribution")
def overdue_distribution(
    request: Request,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = stats_service.overdue_distribution(db, principal, start_at=start_at, end_at=end_at)
    return ok(request, data)
