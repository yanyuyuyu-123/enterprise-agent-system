"""T42–T43：半挂车队 Agent（查车、统计、报告、派车申请与审批）。"""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.agents import supervisor, vehicle_agent
from app.core.db import SessionLocal
from app.models.org import User
from app.models.vehicle import CarApplication, Vehicle
from app.services import vehicle_service
from app.services.permission_service import Principal, load_principal
from tests.helpers import chat


def _principal(employee_no: str) -> Principal:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.employee_no == employee_no))
        assert user is not None
        return load_principal(db, user)
    finally:
        db.close()


def test_t42_vehicle_agent_queries_and_stats() -> None:
    # 车辆说法优先归车辆域，不被财务/运营抢走
    assert supervisor.route_domain("现在有哪些车能派？") == "vehicle"
    assert supervisor.route_domain("按项目统计一下今年的用车费用") == "vehicle"
    assert supervisor.route_domain("明天上午9点从打通煤矿到珞璜电厂，帮我申请派车") == "vehicle"
    assert supervisor.route_domain("写一份上个月的车队运输报告") == "vehicle"
    assert supervisor.route_domain("现在有哪些半挂车能派？") == "vehicle"

    db = SessionLocal()
    try:
        principal = _principal("M0001")

        # 查车：可派车辆列表
        answer = vehicle_agent.run(db, principal, "现在有哪些车能派？")["answer"]
        assert "台车" in answer and "可派" in answer, answer

        listed = vehicle_service.list_vehicles(db, principal, page_size=50)
        assert listed["total"] >= 6, listed
        assert all(item["trailer_no"] for item in listed["items"]), listed
        assert all(item["vehicle_type"] == "tractor" for item in listed["items"]), listed
        available = vehicle_service.list_vehicles(
            db, principal, status="available", page_size=50
        )
        assert available["items"], available
        assert all(item["status"] == "available" for item in available["items"])

        # 统计：总览次数必须与明细行数一致，不能因联表翻倍
        year_start = date(date.today().year, 1, 1)
        stats = vehicle_service.usage_stats(db, principal, start_date=year_start)
        expected = db.scalar(
            select(func.count(CarApplication.id)).where(
                CarApplication.deleted_at.is_(None),
                CarApplication.status.in_(("approved", "completed")),
                CarApplication.start_time
                >= datetime.combine(year_start, datetime.min.time(), tzinfo=ZoneInfo("Asia/Shanghai")),
            )
        )
        assert stats["summary"]["trips"] == int(expected or 0), stats["summary"]
        assert stats["summary"]["trips"] > 0, stats["summary"]

        by_project = vehicle_service.usage_stats(
            db, principal, start_date=year_start, group_by="project"
        )
        assert by_project["groups"], by_project
        assert all(group["name"] for group in by_project["groups"])

        # 报告走 fallback（测试环境无模型），数字与统计口径一致
        report = vehicle_agent.run(db, principal, "写一份上个月的车队运输报告")
        assert report["answer"].startswith("截至") or "半挂车队运输报告" in report["answer"]
        assert "总费用" in report["answer"], report["answer"]
        assert "吨" in report["answer"], report["answer"]
    finally:
        db.close()


def test_t43_vehicle_application_create_and_approve(client, tokens) -> None:
    token = tokens("M0001")
    _, pending = chat(
        client,
        token,
        message="明天上午9点从打通煤矿到珞璜电厂，拉32吨精煤，帮我申请派车",
    )
    assert pending and pending.get("confirmation"), pending
    card = pending["confirmation"]
    assert card["action"] == "vehicle.create_application", card
    assert "打通煤矿" in card["summary"] and "珞璜电厂" in card["summary"], card
    assert card["params"]["cargo"] == "精煤", card
    assert card["params"]["tonnage"] == 32, card

    _, done = chat(client, token, confirm_token=card["confirm_token"])
    assert done and "已提交" in done["answer"], done
    match = re.search(r"CA\d{8,}", done["answer"])
    assert match, done["answer"]
    application_no = match.group(0)

    db = SessionLocal()
    try:
        principal = _principal("M0001")
        row = vehicle_service.get_application(db, principal, application_no)
        assert row.status == "pending"
        assert row.cargo == "精煤"
        assert str(row.tonnage) == "32.0"

        # 待审批列表里能看到刚提交的申请
        listed = vehicle_agent.run(db, principal, "待审批的派车申请有哪些")["answer"]
        assert application_no in listed, listed

        # 审批并派车
        plate = vehicle_service.list_vehicles(
            db, principal, status="available", page_size=1
        )["items"][0]["plate_no"]
    finally:
        db.close()

    _, approve_card = chat(
        client, token, message=f"批准派车申请 {application_no}，派车 {plate}"
    )
    assert approve_card and approve_card.get("confirmation"), approve_card
    assert approve_card["confirmation"]["params"]["plate_no"] == plate, approve_card

    _, approved = chat(
        client, token, confirm_token=approve_card["confirmation"]["confirm_token"]
    )
    assert approved and "已批准" in approved["answer"], approved
    assert plate in approved["answer"], approved

    db = SessionLocal()
    try:
        principal = _principal("M0001")
        row = vehicle_service.get_application(db, principal, application_no)
        assert row.status == "approved"
        assert row.plate_no == plate
        vehicle = db.scalar(select(Vehicle).where(Vehicle.plate_no == plate))
        assert vehicle is not None and vehicle.status == "in_use"
    finally:
        db.close()

    # 重复审批会被拦截
    _, again = chat(client, token, message=f"批准派车申请 {application_no}")
    assert again and "不需要再审批" in again["answer"], again


def test_t44_vehicle_permissions(client, tokens) -> None:
    """生产工人可提派车申请，但不能查看车辆档案。"""
    from app.core.errors import AppError
    from app.tools.executor import execute_tool

    _, denied = chat(client, tokens("V2K01"), message="现在有哪些车能派？")
    assert denied and "权限" in denied["answer"], denied

    result, _meta = execute_tool("vehicle.list", {}, _principal("V2K01"), timeout_s=10)
    assert result["ok"] is False, result

    db = SessionLocal()
    try:
        try:
            vehicle_service.list_vehicles(db, _principal("V2K01"))
        except AppError:
            pass
        else:  # pragma: no cover - 权限缺失时必须报错
            raise AssertionError("生产工人不应有车辆档案权限")
    finally:
        db.close()
