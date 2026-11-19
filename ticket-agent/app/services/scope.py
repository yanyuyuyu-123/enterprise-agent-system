from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.constants import (
    SCOPE_BUSINESS_DOMAIN,
    SCOPE_COMPANY,
    SCOPE_DEPARTMENT,
    SCOPE_SELF,
    SCOPE_SELF_AND_SUBORDINATES,
)
from app.core.errors import AppError
from app.models.org import User
from app.models.work_order import WorkOrder
from app.services.permission_service import Principal


def _subordinate_ids(principal: Principal):
    return select(User.id).where(
        User.manager_id == principal.user_id,
        User.deleted_at.is_(None),
    )


def work_order_scope_condition(principal: Principal, scope: str):
    """把 data_scope 翻译成 work_orders 过滤条件；None 表示不加条件。"""
    if scope == SCOPE_COMPANY:
        return None

    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        return WorkOrder.department_id == principal.department_id

    if scope == SCOPE_SELF_AND_SUBORDINATES:
        return or_(
            WorkOrder.creator_id == principal.user_id,
            WorkOrder.assignee_id == principal.user_id,
            WorkOrder.creator_id.in_(_subordinate_ids(principal)),
        )

    if scope == SCOPE_SELF:
        return or_(
            WorkOrder.creator_id == principal.user_id,
            WorkOrder.assignee_id == principal.user_id,
        )

    raise AppError(2002, "超出数据范围", 403)


def apply_work_order_scope(stmt: Select, principal: Principal, scope: str) -> Select:
    condition = work_order_scope_condition(principal, scope)
    return stmt if condition is None else stmt.where(condition)


def owner_scope_condition(principal: Principal, scope: str, owner_column):
    """主数据按归属人过滤：self 本人、department 同部门、company 不限。"""
    if scope == SCOPE_COMPANY:
        return None
    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        return owner_column.in_(
            select(User.id).where(
                User.department_id == principal.department_id,
                User.deleted_at.is_(None),
            )
        )
    if scope == SCOPE_SELF_AND_SUBORDINATES:
        return or_(owner_column == principal.user_id, owner_column.in_(_subordinate_ids(principal)))
    if scope == SCOPE_SELF:
        return owner_column == principal.user_id
    raise AppError(2002, "超出数据范围", 403)


def ensure_owner_visible(
    db: Session, principal: Principal, scope: str, owner_id: int | None
) -> None:
    """单条主数据的范围校验，与 owner_scope_condition 口径一致。"""
    if scope == SCOPE_COMPANY:
        return
    if scope == SCOPE_SELF:
        if owner_id != principal.user_id:
            raise AppError(2002, "超出数据范围", 403)
        return
    if scope == SCOPE_DEPARTMENT:
        if owner_id is None or principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        department_id = db.scalar(
            select(User.department_id).where(User.id == owner_id, User.deleted_at.is_(None))
        )
        if department_id != principal.department_id:
            raise AppError(2002, "超出数据范围", 403)
        return
    raise AppError(2002, "超出数据范围", 403)


def department_scope_condition(principal: Principal, scope: str, department_column, person_column):
    """单据按部门/经办人过滤。"""
    if scope in (SCOPE_COMPANY, SCOPE_BUSINESS_DOMAIN):
        # 业务域授权天然覆盖该资源全部数据，不再叠加通用范围
        return None
    if scope == SCOPE_DEPARTMENT:
        if principal.department_id is None:
            raise AppError(2002, "超出数据范围", 403)
        return department_column == principal.department_id
    if scope == SCOPE_SELF_AND_SUBORDINATES:
        return or_(
            person_column == principal.user_id,
            person_column.in_(_subordinate_ids(principal)),
        )
    if scope == SCOPE_SELF:
        return person_column == principal.user_id
    raise AppError(2002, "超出数据范围", 403)
