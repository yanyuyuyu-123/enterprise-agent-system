"""车辆工具：查车、发运统计、报告数据、派车申请与审批。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services import vehicle_service
from app.services.permission_service import Principal, require_permission


def _ok(data: Any, message: str = "ok") -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "source": {"type": "vehicle"},
        "message": message,
    }


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def tool_vehicle_list(db: Session, principal: Principal, args: dict[str, Any]) -> dict[str, Any]:
    data = vehicle_service.list_vehicles(
        db,
        principal,
        keyword=args.get("keyword"),
        status=args.get("status"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 20),
    )
    return _ok(data)


def tool_vehicle_usage_stats(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = vehicle_service.usage_stats(
        db,
        principal,
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        group_by=str(args.get("group_by") or "car"),
    )
    return _ok(data)


def tool_vehicle_report_data(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = vehicle_service.report_data(
        db,
        principal,
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
    )
    return _ok(data)


def tool_car_application_list(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = vehicle_service.list_applications(
        db,
        principal,
        status=args.get("status"),
        keyword=args.get("keyword"),
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or 20),
    )
    return _ok(data)


def tool_create_car_application(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    data = vehicle_service.create_application(db, principal, args)
    return _ok(data, f"派车申请 {data['application_no']} 已提交")


def tool_approve_car_application(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "car_application", "approve")
    data = vehicle_service.approve_application(
        db,
        principal,
        str(args.get("application_no") or ""),
        decision=str(args.get("decision") or ""),
        comment=args.get("comment"),
        vehicle_value=args.get("plate_no"),
    )
    return _ok(data, f"派车申请 {data['application_no']} 审批完成")
