"""工单 Agent 工具实现。

工具只调用 service 层，与 HTTP 接口共用权限、范围与状态机；这里不写 SQL 业务
查询（设备、人员解析除外，仅做主数据查找）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import CATEGORY_ASSIGNEE_POSITIONS, CATEGORY_DEVICE_REPAIR
from app.core.errors import AppError
from app.models.org import Position, User, UserPosition
from app.models.work_order import Device, WorkOrder
from app.schemas.work_order import AssignIn, ReviewIn, SubmitIn, WorkOrderCreate
from app.services import work_order_service
from app.services.flow_service import get_config_int
from app.services.permission_service import Principal


def _ok(data: Any, *, source: dict[str, Any], message: str = "ok") -> dict[str, Any]:
    return {"ok": True, "data": data, "source": source, "message": message}


def find_device(
    db: Session, *, device_no: str | None = None, device_name: str | None = None
) -> Device | None:
    stmt = select(Device).where(Device.deleted_at.is_(None))
    if device_no:
        stmt = stmt.where(Device.device_no == device_no)
    elif device_name:
        stmt = stmt.where(Device.device_name == device_name)
    else:
        return None
    return db.scalar(stmt.order_by(Device.id).limit(1))


def find_active_users(
    db: Session, *, name: str | None = None, employee_no: str | None = None
) -> list[User]:
    if not name and not employee_no:
        return []
    stmt = select(User).where(User.status == "active", User.deleted_at.is_(None))
    if employee_no:
        stmt = stmt.where(User.employee_no == employee_no)
    if name:
        stmt = stmt.where(User.name == name)
    return list(db.scalars(stmt.order_by(User.id).limit(10)).all())


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def assign_candidates(db: Session, order: WorkOrder) -> list[dict[str, Any]]:
    codes = CATEGORY_ASSIGNEE_POSITIONS.get(order.category)
    if not codes:
        return []
    rows = db.execute(
        select(User.id, User.name, User.employee_no, Position.name)
        .join(UserPosition, UserPosition.user_id == User.id)
        .join(Position, Position.id == UserPosition.position_id)
        .where(
            Position.code.in_(codes),
            Position.is_active.is_(True),
            Position.deleted_at.is_(None),
            UserPosition.deleted_at.is_(None),
            User.status == "active",
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
    ).all()
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for user_id, name, employee_no, position_name in rows:
        if user_id in seen:
            continue
        seen.add(user_id)
        result.append(
            {
                "user_id": user_id,
                "name": name,
                "employee_no": employee_no,
                "position_name": position_name,
            }
        )
    return result


def tool_query(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    data = work_order_service.list_orders(
        db,
        principal,
        status=args.get("status"),
        category=args.get("category"),
        priority=args.get("priority"),
        keyword=args.get("keyword"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 10),
    )
    ids = [item["order_no"] for item in data["items"]]
    return _ok(
        data,
        source={"type": "work_order", "ids": ids},
        message=f"共 {data['total']} 条",
    )


def tool_detail(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    order = work_order_service.visible_order_by_no(db, principal, args["order_no"])
    data = work_order_service.get_order(db, principal, order.id)
    return _ok(data, source={"type": "work_order", "ids": [order.order_no]})


def tool_summary(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    order = work_order_service.visible_order_by_no(db, principal, args["order_no"])
    data = work_order_service.get_order(db, principal, order.id)
    repeat_count = 0
    if order.category == CATEGORY_DEVICE_REPAIR and order.source_id is not None:
        days = get_config_int(db, "work_order.repeat.period_days", 30)
        since = datetime.now(UTC) - timedelta(days=days)
        repeat_count = int(
            db.scalar(
                select(func.count())
                .select_from(WorkOrder)
                .where(
                    WorkOrder.id != order.id,
                    WorkOrder.category == CATEGORY_DEVICE_REPAIR,
                    WorkOrder.source_id == order.source_id,
                    WorkOrder.created_at >= since,
                    WorkOrder.deleted_at.is_(None),
                )
            )
            or 0
        )
    data["repeat_count"] = repeat_count
    data["repeat_period_days"] = get_config_int(db, "work_order.repeat.period_days", 30)
    return _ok(data, source={"type": "work_order", "ids": [order.order_no]})


def tool_assign_candidates(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order = work_order_service.visible_order_by_no(db, principal, args["order_no"])
    candidates = assign_candidates(db, order)
    message = "该类别无需分配" if not candidates else f"候选 {len(candidates)} 人"
    return _ok(
        {"order_no": order.order_no, "category": order.category, "candidates": candidates},
        source={"type": "work_order", "ids": [order.order_no]},
        message=message,
    )


def tool_create(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    category = str(args["category"])
    values: dict[str, Any] = {
        "category": category,
        "title": args["title"],
        "description": args.get("description"),
        "priority": args.get("priority") or "normal",
    }
    if category == CATEGORY_DEVICE_REPAIR:
        values["device"] = {
            "device_id": args.get("device_id"),
            "fault_description": args.get("fault_description"),
        }
    elif category == "expense_reimbursement":
        values["expense"] = {
            "expense_type": args.get("expense_type"),
            "amount": parse_amount(args.get("amount")),
        }
    elif category == "security_patrol":
        values["patrol"] = {
            "patrol_area": args.get("patrol_area"),
            "hazard_description": args.get("hazard_description"),
        }
    elif category == "transport_exception":
        values["transport"] = {
            "trip_no": args.get("trip_no"),
            "exception_type": args.get("exception_type"),
        }

    payload = WorkOrderCreate(**values)
    data = work_order_service.create(db, payload, principal)
    return _ok(
        data,
        source={"type": "work_order", "ids": [data["order_no"]]},
        message="工单已创建",
    )


def tool_assign(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    payload = AssignIn(
        version=int(args["version"]),
        assignee_id=int(args["assignee_id"]),
        comment=args.get("comment"),
    )
    data = work_order_service.assign(db, principal, int(args["work_order_id"]), payload)
    return _ok(
        data,
        source={"type": "work_order", "ids": [data["order_no"]]},
        message="工单已分配",
    )


def tool_submit(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    order = work_order_service.visible_order(db, principal, int(args["work_order_id"]))
    values: dict[str, Any] = {
        "version": int(args["version"]),
        "content": str(args["content"]),
    }
    result_field = work_order_service.RESULT_FIELD.get(order.category)
    if result_field is not None:
        values[result_field] = args.get("result") or args["content"]
    data = work_order_service.submit(db, principal, order.id, SubmitIn(**values))
    return _ok(
        data,
        source={"type": "work_order", "ids": [data["order_no"]]},
        message="处理结果已提交",
    )


def tool_review(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    order = work_order_service.visible_order(db, principal, int(args["work_order_id"]))
    decision = str(args.get("decision") or "").strip()
    if decision not in ("approve", "reject"):
        raise AppError(1001, "审核结果只能是通过或驳回", 400)
    if decision == "reject" and not str(args.get("comment") or "").strip():
        raise AppError(1001, "驳回必须填写意见", 400)
    data = work_order_service.review(
        db,
        principal,
        order.id,
        ReviewIn(
            version=int(args["version"]),
            result=decision,
            comment=args.get("comment"),
        ),
    )
    return _ok(
        data,
        source={"type": "work_order", "ids": [data["order_no"]]},
        message="审核完成",
    )


def parse_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def ensure_order_no(args: dict[str, Any]) -> str:
    order_no = str(args.get("order_no") or "").strip()
    if not order_no:
        raise AppError(1001, "请提供工单号", 422)
    return order_no


def search_users_by_name(db: Session, text: str) -> list[User]:
    like = f"%{text}%"
    return list(
        db.scalars(
            select(User)
            .where(
                or_(User.name.ilike(like), User.employee_no.ilike(like)),
                User.status == "active",
                User.deleted_at.is_(None),
            )
            .order_by(User.id)
            .limit(10)
        ).all()
    )
