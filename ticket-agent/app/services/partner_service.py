from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import Customer, Supplier
from app.schemas.business import (
    CustomerCreate,
    CustomerUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.services.log_service import write_log_safely
from app.services.permission_service import Principal, require_permission
from app.services.scope import ensure_owner_visible, owner_scope_condition


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _supplier_payload(row: Supplier) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "address": row.address,
        "payment_type": row.payment_type,
        "status": row.status,
        "owner_id": row.owner_id,
        "is_mock": row.is_mock,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _customer_payload(row: Customer) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "address": row.address,
        "credit_limit": str(row.credit_limit),
        "status": row.status,
        "owner_id": row.owner_id,
        "is_mock": row.is_mock,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _paged(stmt, page: int, page_size: int, db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def list_suppliers(
    db: Session,
    principal: Principal,
    *,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "supplier", "read")
    stmt = select(Supplier).where(Supplier.deleted_at.is_(None))
    condition = owner_scope_condition(principal, scope, Supplier.owner_id)
    if condition is not None:
        stmt = stmt.where(condition)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Supplier.code.ilike(like), Supplier.name.ilike(like)))
    if status:
        stmt = stmt.where(Supplier.status == status)
    result = _paged(stmt.order_by(Supplier.id.desc()), page, page_size, db)
    result["items"] = [_supplier_payload(row) for row in result["items"]]
    return result


def get_supplier(db: Session, principal: Principal, supplier_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "supplier", "read")
    row = db.get(Supplier, supplier_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "供应商不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    return _supplier_payload(row)


def create_supplier(db: Session, principal: Principal, payload: SupplierCreate) -> dict[str, Any]:
    require_permission(principal, "supplier", "create")
    exists = db.scalar(
        select(Supplier.id).where(Supplier.code == payload.code, Supplier.deleted_at.is_(None))
    )
    if exists is not None:
        raise AppError(3000, "供应商编码已存在", 409)
    row = Supplier(
        **payload.model_dump(exclude={"owner_id"}),
        owner_id=payload.owner_id or principal.user_id,
    )
    db.add(row)
    db.flush()
    write_log_safely(
        db,
        resource="supplier",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="supplier",
        target_id=row.code,
    )
    db.commit()
    return _supplier_payload(row)


def update_supplier(
    db: Session, principal: Principal, supplier_id: int, payload: SupplierUpdate
) -> dict[str, Any]:
    scope = require_permission(principal, "supplier", "update")
    row = db.get(Supplier, supplier_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "供应商不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    write_log_safely(
        db,
        resource="supplier",
        action="update",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="supplier",
        target_id=row.code,
    )
    db.commit()
    return _supplier_payload(row)


def list_customers(
    db: Session,
    principal: Principal,
    *,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "customer", "read")
    stmt = select(Customer).where(Customer.deleted_at.is_(None))
    condition = owner_scope_condition(principal, scope, Customer.owner_id)
    if condition is not None:
        stmt = stmt.where(condition)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Customer.code.ilike(like), Customer.name.ilike(like)))
    if status:
        stmt = stmt.where(Customer.status == status)
    result = _paged(stmt.order_by(Customer.id.desc()), page, page_size, db)
    result["items"] = [_customer_payload(row) for row in result["items"]]
    return result


def get_customer(db: Session, principal: Principal, customer_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "customer", "read")
    row = db.get(Customer, customer_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "客户不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    return _customer_payload(row)


def create_customer(db: Session, principal: Principal, payload: CustomerCreate) -> dict[str, Any]:
    require_permission(principal, "customer", "create")
    exists = db.scalar(
        select(Customer.id).where(Customer.code == payload.code, Customer.deleted_at.is_(None))
    )
    if exists is not None:
        raise AppError(3000, "客户编码已存在", 409)
    row = Customer(
        **payload.model_dump(exclude={"owner_id"}),
        owner_id=payload.owner_id or principal.user_id,
    )
    db.add(row)
    db.flush()
    write_log_safely(
        db,
        resource="customer",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="customer",
        target_id=row.code,
    )
    db.commit()
    return _customer_payload(row)


def update_customer(
    db: Session, principal: Principal, customer_id: int, payload: CustomerUpdate
) -> dict[str, Any]:
    scope = require_permission(principal, "customer", "update")
    row = db.get(Customer, customer_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "客户不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    write_log_safely(
        db,
        resource="customer",
        action="update",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="customer",
        target_id=row.code,
    )
    db.commit()
    return _customer_payload(row)
