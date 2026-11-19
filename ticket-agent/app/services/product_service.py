from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import Product
from app.schemas.business import ProductCreate, ProductUpdate
from app.services.log_service import write_log_safely
from app.services.permission_service import Principal, require_permission
from app.services.scope import ensure_owner_visible, owner_scope_condition


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _payload(row: Product) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "spec": row.spec,
        "unit": row.unit,
        "category": row.category,
        "purchase_price": str(row.purchase_price),
        "sale_price": str(row.sale_price),
        "is_active": row.is_active,
        "owner_id": row.owner_id,
        "is_mock": row.is_mock,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def list_products(
    db: Session,
    principal: Principal,
    *,
    keyword: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    scope = require_permission(principal, "product", "read")
    stmt = select(Product).where(Product.deleted_at.is_(None))
    condition = owner_scope_condition(principal, scope, Product.owner_id)
    if condition is not None:
        stmt = stmt.where(condition)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Product.code.ilike(like), Product.name.ilike(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    if is_active is not None:
        stmt = stmt.where(Product.is_active.is_(is_active))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_product(db: Session, principal: Principal, product_id: int) -> dict[str, Any]:
    scope = require_permission(principal, "product", "read")
    row = db.get(Product, product_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "产品不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    return _payload(row)


def create_product(db: Session, principal: Principal, payload: ProductCreate) -> dict[str, Any]:
    require_permission(principal, "product", "create")
    exists = db.scalar(
        select(Product.id).where(Product.code == payload.code, Product.deleted_at.is_(None))
    )
    if exists is not None:
        raise AppError(3000, "产品编码已存在", 409)
    row = Product(
        **payload.model_dump(exclude={"owner_id"}),
        owner_id=payload.owner_id or principal.user_id,
    )
    db.add(row)
    db.flush()
    write_log_safely(
        db,
        resource="product",
        action="create",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="product",
        target_id=row.code,
    )
    db.commit()
    return _payload(row)


def update_product(
    db: Session, principal: Principal, product_id: int, payload: ProductUpdate
) -> dict[str, Any]:
    scope = require_permission(principal, "product", "update")
    row = db.get(Product, product_id)
    if row is None or row.deleted_at is not None:
        raise AppError(3003, "产品不存在或不可见", 404)
    ensure_owner_visible(db, principal, scope, row.owner_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    write_log_safely(
        db,
        resource="product",
        action="update",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="important",
        target_type="product",
        target_id=row.code,
    )
    db.commit()
    return _payload(row)
