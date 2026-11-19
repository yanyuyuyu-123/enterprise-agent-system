"""车辆管理：半挂车档案、派车申请、发运统计与报告数据。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.org import Department
from app.models.vehicle import CarApplication, Vehicle
from app.services.doc_no import next_doc_no
from app.services.permission_service import Principal, require_permission
from app.services.scope import department_scope_condition

VEHICLE_STATUS_LABELS = {
    "available": "可派",
    "in_use": "使用中",
    "maintenance": "维修中",
    "disabled": "停用",
}
VEHICLE_TYPE_LABELS = {
    "tractor": "牵引车",
    "dump": "自卸半挂",
    "tanker": "罐式半挂",
    "van": "厢式半挂",
}
APPLICATION_STATUS_LABELS = {
    "pending": "待审批",
    "approved": "已批准",
    "rejected": "已驳回",
    "cancelled": "已取消",
    "completed": "已完成",
}
FEE_FIELDS = ("fuel_cost", "toll_fee", "parking_fee", "other_fee")


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _day_start(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time(), tzinfo=ZoneInfo("Asia/Shanghai"))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return value.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="minutes")


def _money(value: Decimal | int | float | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def vehicle_payload(row: Vehicle) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "plate_no": row.plate_no,
        "model": row.model,
        "vehicle_type": row.vehicle_type,
        "vehicle_type_label": VEHICLE_TYPE_LABELS.get(row.vehicle_type, row.vehicle_type),
        "trailer_no": row.trailer_no,
        "load_ton": f"{Decimal(row.load_ton or 0):.1f}",
        "driver_name": row.driver_name,
        "driver_phone": row.driver_phone,
        "status": row.status,
        "status_label": VEHICLE_STATUS_LABELS.get(row.status, row.status),
        "mileage_km": f"{Decimal(row.mileage_km or 0):.1f}",
        "remark": row.remark,
    }


def application_payload(row: CarApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_no": row.application_no,
        "status": row.status,
        "status_label": APPLICATION_STATUS_LABELS.get(row.status, row.status),
        "applicant_name": row.applicant_name,
        "department_id": row.department_id,
        "start_address": row.start_address,
        "end_address": row.end_address,
        "start_time": _iso(row.start_time),
        "end_time": _iso(row.end_time),
        "cargo": row.cargo,
        "tonnage": f"{Decimal(row.tonnage or 0):.1f}",
        "project": row.project,
        "reason": row.reason,
        "vehicle_id": row.vehicle_id,
        "plate_no": row.plate_no,
        "driver_name": row.driver_name,
        "mileage_km": f"{Decimal(row.mileage_km or 0):.1f}",
        "fuel_cost": _money(row.fuel_cost),
        "toll_fee": _money(row.toll_fee),
        "parking_fee": _money(row.parking_fee),
        "other_fee": _money(row.other_fee),
        "total_cost": _money(row.total_cost),
        "approver_name": row.approver_name,
        "approve_comment": row.approve_comment,
        "approved_at": _iso(row.approved_at),
        "created_at": _iso(row.created_at),
    }


def list_vehicles(
    db: Session,
    principal: Principal,
    *,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    require_permission(principal, "vehicle", "read")
    stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Vehicle.status == status)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Vehicle.plate_no.ilike(like),
                Vehicle.code.ilike(like),
                Vehicle.model.ilike(like),
                Vehicle.driver_name.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Vehicle.code).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [vehicle_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def find_vehicle(db: Session, principal: Principal, value: str) -> Vehicle:
    require_permission(principal, "vehicle", "read")
    keyword = value.strip()
    if not keyword:
        raise AppError(1001, "请提供车辆编码或车牌号", 422)
    rows = db.scalars(
        select(Vehicle).where(
            Vehicle.deleted_at.is_(None),
            or_(Vehicle.code == keyword, Vehicle.plate_no == keyword),
        )
    ).all()
    if not rows:
        like = f"%{keyword}%"
        rows = db.scalars(
            select(Vehicle).where(
                Vehicle.deleted_at.is_(None),
                or_(Vehicle.plate_no.ilike(like), Vehicle.code.ilike(like)),
            )
        ).all()
    if not rows:
        raise AppError(3003, f"没有找到车辆“{value}”", 404)
    if len(rows) > 1:
        plates = "、".join(row.plate_no for row in rows)
        raise AppError(3000, f"车辆“{value}”匹配到多台（{plates}），请写完整车牌", 409)
    return rows[0]


def _application_scope(principal: Principal, stmt):
    scope = require_permission(principal, "car_application", "read")
    condition = department_scope_condition(
        principal, scope, CarApplication.department_id, CarApplication.applicant_id
    )
    return stmt if condition is None else stmt.where(condition)


def list_applications(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    stmt = select(CarApplication).where(CarApplication.deleted_at.is_(None))
    stmt = _application_scope(principal, stmt)
    if status:
        stmt = stmt.where(CarApplication.status == status)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                CarApplication.application_no.ilike(like),
                CarApplication.start_address.ilike(like),
                CarApplication.end_address.ilike(like),
                CarApplication.project.ilike(like),
                CarApplication.applicant_name.ilike(like),
            )
        )
    if start_date is not None:
        stmt = stmt.where(CarApplication.start_time >= _day_start(start_date))
    if end_date is not None:
        stmt = stmt.where(CarApplication.start_time < _day_start(end_date + timedelta(days=1)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(CarApplication.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [application_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_application(db: Session, principal: Principal, application_no: str) -> CarApplication:
    stmt = select(CarApplication).where(
        CarApplication.deleted_at.is_(None),
        CarApplication.application_no == application_no.strip().upper(),
    )
    stmt = _application_scope(principal, stmt)
    row = db.scalar(stmt)
    if row is None:
        raise AppError(3003, f"派车申请 {application_no} 不存在或不可见", 404)
    return row


def _parse_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    text = str(value or "").strip()
    if not text:
        raise AppError(1001, f"请提供{field}", 422)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AppError(1001, f"{field}格式应为 YYYY-MM-DD HH:MM", 422) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))


def create_application(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_permission(principal, "car_application", "create")
    start_address = str(payload.get("start_address") or "").strip()
    end_address = str(payload.get("end_address") or "").strip()
    if not start_address or not end_address:
        raise AppError(1001, "请提供装货地和卸货地", 422)
    start_time = _parse_datetime(payload.get("start_time"), "计划发车时间")
    end_time = _parse_datetime(
        payload.get("end_time") or start_time + timedelta(hours=8), "计划到达时间"
    )
    if end_time <= start_time:
        raise AppError(1001, "结束时间必须晚于开始时间", 422)
    try:
        tonnage = Decimal(str(payload.get("tonnage") or 0))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(1001, "载货吨位必须是数字", 422) from exc
    if tonnage < 0:
        raise AppError(1001, "载货吨位不能为负数", 422)

    row = CarApplication(
        application_no=next_doc_no(db, "CA", "CA"),
        applicant_id=principal.user_id,
        applicant_name=principal.name,
        department_id=principal.department_id,
        start_address=start_address,
        end_address=end_address,
        start_time=start_time,
        end_time=end_time,
        cargo=str(payload.get("cargo") or "").strip() or None,
        tonnage=tonnage,
        project=str(payload.get("project") or "").strip() or None,
        reason=str(payload.get("reason") or "").strip() or None,
        status="pending",
        remark=str(payload.get("remark") or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return application_payload(row)


def approve_application(
    db: Session,
    principal: Principal,
    application_no: str,
    *,
    decision: str,
    comment: str | None = None,
    vehicle_value: str | None = None,
) -> dict[str, Any]:
    require_permission(principal, "car_application", "approve")
    if decision not in ("approve", "reject"):
        raise AppError(1001, "审批结论只能是批准或驳回", 422)
    row = get_application(db, principal, application_no)
    if row.status != "pending":
        label = APPLICATION_STATUS_LABELS.get(row.status, row.status)
        raise AppError(3001, f"申请 {row.application_no} 当前是{label}，不能重复审批", 409)
    if decision == "reject" and not str(comment or "").strip():
        raise AppError(3000, "驳回必须填写原因", 409)

    row.status = "approved" if decision == "approve" else "rejected"
    row.approver_id = principal.user_id
    row.approver_name = principal.name
    row.approve_comment = str(comment or "").strip() or None
    row.approved_at = _now()
    if decision == "approve" and vehicle_value:
        vehicle = find_vehicle(db, principal, vehicle_value)
        if vehicle.status != "available":
            label = VEHICLE_STATUS_LABELS.get(vehicle.status, vehicle.status)
            raise AppError(3000, f"车辆 {vehicle.plate_no} 当前{label}，不可派车", 409)
        row.vehicle_id = vehicle.id
        row.plate_no = vehicle.plate_no
        row.driver_name = vehicle.driver_name
        vehicle.status = "in_use"
    db.commit()
    db.refresh(row)
    return application_payload(row)


def _trip_filter(stmt, start_date: date | None, end_date: date | None):
    stmt = stmt.where(CarApplication.status.in_(("approved", "completed")))
    if start_date is not None:
        stmt = stmt.where(CarApplication.start_time >= _day_start(start_date))
    if end_date is not None:
        stmt = stmt.where(CarApplication.start_time < _day_start(end_date + timedelta(days=1)))
    return stmt


def usage_stats(
    db: Session,
    principal: Principal,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: str = "car",
) -> dict[str, Any]:
    """按车辆/项目/部门/月份统计发运车次、里程、吨位与费用。"""
    require_permission(principal, "car_application", "read")
    summary_stmt = select(
        func.count(CarApplication.id),
        func.coalesce(func.sum(CarApplication.mileage_km), 0),
        func.coalesce(func.sum(CarApplication.tonnage), 0),
        func.coalesce(func.sum(CarApplication.fuel_cost), 0),
        func.coalesce(func.sum(CarApplication.toll_fee), 0),
        func.coalesce(func.sum(CarApplication.parking_fee), 0),
        func.coalesce(func.sum(CarApplication.other_fee), 0),
        func.coalesce(func.sum(CarApplication.total_cost), 0),
    ).where(CarApplication.deleted_at.is_(None))
    summary_stmt = _application_scope(principal, summary_stmt)
    summary_stmt = _trip_filter(summary_stmt, start_date, end_date)
    trips, mileage, tonnage, fuel, toll, parking, other, total = db.execute(
        summary_stmt
    ).one()
    summary = {
        "trips": int(trips or 0),
        "mileage_km": f"{Decimal(mileage or 0):.1f}",
        "tonnage": f"{Decimal(tonnage or 0):.1f}",
        "fuel_cost": _money(fuel),
        "toll_fee": _money(toll),
        "parking_fee": _money(parking),
        "other_fee": _money(other),
        "total_cost": _money(total),
    }

    if group_by == "month":
        key = func.to_char(CarApplication.start_time, "YYYY-MM")
    elif group_by == "project":
        key = func.coalesce(CarApplication.project, "未指定项目")
    elif group_by == "dept":
        key = func.coalesce(Department.name, "未分配部门")
    else:
        key = func.coalesce(CarApplication.plate_no, "未派车")
        group_by = "car"

    stmt = (
        select(
            key.label("name"),
            func.count(CarApplication.id).label("trips"),
            func.coalesce(func.sum(CarApplication.mileage_km), 0).label("mileage"),
            func.coalesce(func.sum(CarApplication.total_cost), 0).label("cost"),
        )
        .where(CarApplication.deleted_at.is_(None))
        .group_by(key)
        .order_by(func.sum(CarApplication.total_cost).desc())
    )
    stmt = _application_scope(principal, stmt)
    stmt = _trip_filter(stmt, start_date, end_date)
    if group_by == "dept":
        stmt = stmt.join(Department, Department.id == CarApplication.department_id)
        stmt = stmt.group_by(Department.name)
    rows = db.execute(stmt).all()
    groups = [
        {
            "name": str(row.name),
            "trips": int(row.trips),
            "mileage_km": f"{Decimal(row.mileage or 0):.1f}",
            "total_cost": _money(row.cost),
        }
        for row in rows
    ]
    return {"group_by": group_by, "summary": summary, "groups": groups}


def report_data(
    db: Session, principal: Principal, *, start_date: date | None = None, end_date: date | None = None
) -> dict[str, Any]:
    """报告所需的全量数据：总览、按车、按项目、按部门、按月、车辆状态。"""
    overview = usage_stats(
        db, principal, start_date=start_date, end_date=end_date, group_by="car"
    )
    by_project = usage_stats(
        db, principal, start_date=start_date, end_date=end_date, group_by="project"
    )
    by_dept = usage_stats(db, principal, start_date=start_date, end_date=end_date, group_by="dept")
    by_month = usage_stats(
        db, principal, start_date=start_date, end_date=end_date, group_by="month"
    )
    vehicles = list_vehicles(db, principal, page=1, page_size=100)
    status_count: dict[str, int] = {}
    for item in vehicles["items"]:
        status_count[item["status_label"]] = status_count.get(item["status_label"], 0) + 1
    return {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "summary": overview["summary"],
        "by_car": overview["groups"],
        "by_project": by_project["groups"],
        "by_dept": by_dept["groups"],
        "by_month": by_month["groups"],
        "vehicle_status": status_count,
        "vehicle_total": vehicles["total"],
    }
