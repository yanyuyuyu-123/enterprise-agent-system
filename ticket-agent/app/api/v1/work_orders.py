from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.schemas.work_order import (
    AssignIn,
    RecallIn,
    ReviewIn,
    SubmitIn,
    SupplementIn,
    TransferDecisionIn,
    TransferIn,
    VersionedIn,
    WorkOrderCreate,
)
from app.services import work_order_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/work_orders", tags=["work_orders"])


@router.get("")
def list_orders(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = work_order_service.list_orders(
        db,
        principal,
        status=status,
        category=category,
        priority=priority,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("")
def create_order(
    payload: WorkOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.create(db, payload, principal), status_code=201)


@router.get("/{order_id}")
def get_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.get_order(db, principal, order_id))


@router.post("/{order_id}/supplement")
def supplement(
    order_id: int,
    payload: SupplementIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.supplement(db, principal, order_id, payload))


@router.post("/{order_id}/revise")
def revise(
    order_id: int,
    payload: SupplementIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.revise(db, principal, order_id, payload))


@router.post("/{order_id}/assign")
def assign(
    order_id: int,
    payload: AssignIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.assign(db, principal, order_id, payload))


@router.post("/{order_id}/reassign")
def reassign(
    order_id: int,
    payload: AssignIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.assign(db, principal, order_id, payload, reassign=True))


@router.post("/{order_id}/start")
def start(
    order_id: int,
    payload: VersionedIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.start(db, principal, order_id, payload.version))


@router.post("/{order_id}/submit")
def submit(
    order_id: int,
    payload: SubmitIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.submit(db, principal, order_id, payload))


@router.post("/{order_id}/review")
def review(
    order_id: int,
    payload: ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.review(db, principal, order_id, payload))


@router.post("/{order_id}/recall")
def recall(
    order_id: int,
    payload: RecallIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.recall(db, principal, order_id, payload))


@router.post("/{order_id}/transfer")
def transfer(
    order_id: int,
    payload: TransferIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.transfer(db, principal, order_id, payload))


@router.post("/{order_id}/transfer/decision")
def transfer_decision(
    order_id: int,
    payload: TransferDecisionIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, work_order_service.transfer_decision(db, principal, order_id, payload))
