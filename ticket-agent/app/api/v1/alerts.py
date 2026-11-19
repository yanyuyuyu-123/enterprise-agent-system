"""V3 异常预警与安全库存接口。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.services import alert_service
from app.services.permission_service import Principal

router = APIRouter(tags=["alert"])


class CloseIn(BaseModel):
    handle_note: str = Field(min_length=1, max_length=500)


class SafeStockIn(BaseModel):
    product_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    safe_quantity: Decimal = Field(ge=0)


@router.get("/alerts")
def list_alerts(
    request: Request,
    status: str | None = None,
    alert_type: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = alert_service.list_alerts(
        db,
        principal,
        status=status,
        alert_type=alert_type,
        start_at=start_at,
        end_at=end_at,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(
    request: Request,
    alert_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, alert_service.acknowledge(db, principal, alert_id))


@router.post("/alerts/{alert_id}/close")
def close_alert(
    request: Request,
    alert_id: int,
    payload: CloseIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(
        request,
        alert_service.close_alert(db, principal, alert_id, handle_note=payload.handle_note),
    )


@router.get("/safe-stock-configs")
def list_safe_stock(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, alert_service.list_safe_stock(db, principal))


@router.put("/safe-stock-configs")
def update_safe_stock(
    request: Request,
    payload: SafeStockIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = alert_service.update_safe_stock(
        db,
        principal,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        safe_quantity=payload.safe_quantity,
    )
    return ok(request, data)
