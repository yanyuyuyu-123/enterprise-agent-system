"""车辆 Agent：查半挂车、发运统计、写报告、提派车申请与审批。"""

from __future__ import annotations

import re
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agents import llm
from app.core.errors import AppError
from app.services import confirm_service, vehicle_service
from app.services.permission_service import Principal, require_permission
from app.tools.executor import execute_tool

TZ = ZoneInfo("Asia/Shanghai")
CAR_NO_RE = re.compile(r"CA\d{8,}", re.IGNORECASE)
PLATE_RE = re.compile(
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
    r"[A-HJ-NP-Z][A-HJ-NP-Z0-9]{4,6}"
)

REPORT_WORDS = ("报告", "汇报", "写一份", "写份", "总结一下", "分析一下")
STATS_WORDS = (
    "里程",
    "费用",
    "出车次数",
    "出车",
    "发运",
    "车次",
    "吨位",
    "油耗",
    "统计",
    "用量",
    "使用情况",
    "花了多少",
    "跑了",
    "跑过",
    "跑一趟",
    "出趟",
)
CREATE_WORDS = (
    "申请派车",
    "派车申请",
    "提派车",
    "申请用车",
    "用车申请",
    "提用车",
    "要车",
    "安排车",
    "派一台",
    "派一辆",
)
LIST_WORDS = (
    "申请记录",
    "我的申请",
    "我的派车",
    "派车记录",
    "用车记录",
    "派车申请",
    "派车单",
    "申请列表",
    "待审批",
    "审批记录",
)
APPROVE_WORDS = ("审批", "批准", "驳回", "不同意")
VEHICLE_WORDS = (
    "车辆",
    "查车",
    "车牌",
    "车况",
    "可派",
    "空闲",
    "车管",
    "车辆状态",
    "有几台车",
    "哪些车",
    "能派",
    "几台",
    "派车",
    "半挂",
    "牵引车",
    "挂车",
    "车队",
)

CARGO_WORDS = (
    ("精煤", "精煤"),
    ("原煤", "原煤"),
    ("焦炭", "焦炭"),
    ("煤", "煤炭"),
    ("砂石", "砂石"),
    ("石料", "砂石"),
    ("钢材", "钢材"),
    ("水泥", "水泥"),
    ("矿石", "矿石"),
)


def _reply(
    answer: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "answer": answer,
        "sources": sources or [],
        "missing": [],
        "confirmation": confirmation,
    }


def _tool(name: str, args: dict[str, Any], principal: Principal) -> tuple[bool, Any, str]:
    result, _meta = execute_tool(name, args, principal, timeout_s=15)
    return bool(result.get("ok")), result.get("data"), str(result.get("message") or "")


def _confirm(
    db: Session,
    principal: Principal,
    session_id: str | None,
    *,
    action: str,
    params: dict[str, Any],
    summary: str,
    prompt: str,
) -> dict[str, Any]:
    if not session_id:
        return _reply(f"识别到写操作：{summary}。请重新发起会话后再确认。")
    card = confirm_service.issue(
        db,
        principal,
        action=action,
        params=params,
        summary=summary,
        session_id=session_id,
    )
    return _reply(prompt, confirmation=card)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(TZ).strftime("%m月%d日 %H:%M")


def _period_label(start: date | None, end: date | None) -> str:
    if start and end:
        if start == end:
            return f"{start.year}年{start.month}月{start.day}日"
        return f"{start.year}年{start.month}月{start.day}日至{end.month}月{end.day}日"
    if start:
        return f"{start.year}年{start.month}月{start.day}日以后"
    if end:
        return f"截至{end.year}年{end.month}月{end.day}日"
    return "全部"


def _date_range(
    text: str, start_date: date | None = None, end_date: date | None = None
) -> tuple[date | None, date | None]:
    if start_date or end_date:
        return start_date, end_date
    today = date.today()
    if "今天" in text:
        return today, today
    if "昨天" in text:
        day = today - timedelta(days=1)
        return day, day
    if "本周" in text or "这周" in text:
        return today - timedelta(days=today.weekday()), today
    if "上周" in text:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if "本月" in text or "这个月" in text:
        return today.replace(day=1), today
    if "上月" in text or "上个月" in text:
        last_end = today.replace(day=1) - timedelta(days=1)
        return last_end.replace(day=1), last_end
    if "今年" in text:
        return today.replace(month=1, day=1), today
    match = re.search(r"(?:最近|近)\s*(\d+)\s*天", text)
    if match:
        return today - timedelta(days=int(match.group(1)) - 1), today
    match = re.search(r"(?:最近|近)\s*(\d+)\s*个?月", text)
    if match:
        return today - timedelta(days=int(match.group(1)) * 30), today
    if "这两天" in text or "近两天" in text:
        return today - timedelta(days=1), today
    if any(
        word in text
        for word in ("这几天", "这些天", "最近几天", "近几天", "最近一周", "近一周", "这阵子", "最近")
    ):
        return today - timedelta(days=6), today
    return None, None


def _parse_when(text: str) -> tuple[datetime | None, datetime | None]:
    """从“明天上午9点”“11月20日下午3点”等说法解析用车起止时间。"""
    today = datetime.now(TZ).date()
    day: date | None = None
    if "大后天" in text:
        day = today + timedelta(days=3)
    elif "后天" in text:
        day = today + timedelta(days=2)
    elif "明天" in text:
        day = today + timedelta(days=1)
    elif "今天" in text:
        day = today
    else:
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if match:
            try:
                day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                day = None
        if day is None:
            match = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
            if match:
                try:
                    day = date(today.year, int(match.group(1)), int(match.group(2)))
                except ValueError:
                    day = None
    if day is None:
        return None, None

    hour: int | None = None
    minute = 0
    match = re.search(r"(上午|早上|中午|下午|晚上)?\s*(\d{1,2})\s*[:：点]\s*(\d{1,2})?", text)
    if match:
        hour = int(match.group(2))
        minute = int(match.group(3) or 0)
        period = match.group(1)
        if period in ("下午", "晚上") and hour < 12:
            hour += 12
        elif period == "中午" and hour < 11:
            hour += 12
    if hour is None:
        for word, value in (("上午", 9), ("早上", 8), ("中午", 12), ("下午", 14), ("晚上", 19)):
            if word in text:
                hour = value
                break
        else:
            hour = 9
    start = datetime.combine(day, dt_time(hour, minute), tzinfo=TZ)
    return start, start + timedelta(hours=4)


def _parse_tonnage(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*吨", text)
    if match:
        return float(match.group(1))
    if "标载" in text:
        return 32.0
    return None


def _parse_cargo(text: str) -> str | None:
    for word, label in CARGO_WORDS:
        if word in text:
            return label
    return None


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _regex_slots(text: str) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    match = re.search(r"从([^，,。；;\s]{2,24}?)(?:出发)?(?:到|去)([^，,。；;\s]{2,24})", text)
    if match:
        slots["start_address"] = match.group(1)
        slots["end_address"] = match.group(2)
    elif match := re.search(r"(?:到|去)([^，,。；;\s]{2,24})", text):
        slots["end_address"] = match.group(1)
    tonnage = _parse_tonnage(text)
    if tonnage:
        slots["tonnage"] = tonnage
    cargo = _parse_cargo(text)
    if cargo:
        slots["cargo"] = cargo
    start, end = _parse_when(text)
    if start:
        slots["start_time"] = start
        slots["end_time"] = end
    for word in ("电煤保供", "入洗调运", "码头疏港", "跨省调运", "冬季保供", "煤炭运输"):
        if word in text:
            slots["reason"] = word
            break
    return slots


def _extract_apply(text: str) -> dict[str, Any]:
    today = date.today().isoformat()
    data: dict[str, Any] = {}
    try:
        data = llm.extract("vehicle_apply.v1.md", f"今天是 {today}。{text}", None)
    except llm.LLMError:
        data = {}
    slots: dict[str, Any] = {
        "start_address": str(data.get("start_address") or "").strip(),
        "end_address": str(data.get("end_address") or "").strip(),
        "cargo": str(data.get("cargo") or "").strip() or None,
        "tonnage": data.get("tonnage"),
        "project": str(data.get("project") or "").strip() or None,
        "reason": str(data.get("reason") or "").strip() or None,
    }
    start = _parse_datetime(data.get("start_time"))
    end = _parse_datetime(data.get("end_time"))
    fallback = _regex_slots(text)
    if not slots["start_address"] and fallback.get("start_address"):
        slots["start_address"] = fallback["start_address"]
    if not slots["end_address"] and fallback.get("end_address"):
        slots["end_address"] = fallback["end_address"]
    if not slots["cargo"] and fallback.get("cargo"):
        slots["cargo"] = fallback["cargo"]
    if not _as_float(slots["tonnage"]) and fallback.get("tonnage"):
        slots["tonnage"] = fallback["tonnage"]
    if start is None:
        start = fallback.get("start_time")
    if end is None:
        end = fallback.get("end_time")
    if start is None:
        start, end = _parse_when(text)
    slots["start_time"] = start
    slots["end_time"] = end or (start + timedelta(hours=8) if start else None)
    if not slots["reason"] and fallback.get("reason"):
        slots["reason"] = fallback["reason"]
    return slots


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ)


def _handle_create(
    db: Session, principal: Principal, text: str, session_id: str | None
) -> dict[str, Any]:
    slots = _extract_apply(text)
    missing = []
    if not slots["start_address"]:
        missing.append("装货地")
    if not slots["end_address"]:
        missing.append("卸货地")
    if slots["start_time"] is None:
        missing.append("计划发车时间")
    if missing:
        return _reply(
            f"还差：{'、'.join(missing)}。给我一句话就行，例如："
            "明天上午9点从打通煤矿到珞璜电厂，拉32吨精煤，申请派车。"
        )

    start: datetime = slots["start_time"]
    end: datetime = slots["end_time"] or start + timedelta(hours=8)
    if start < datetime.now(TZ) - timedelta(minutes=30):
        return _reply(f"开始时间 {_fmt_dt(start)} 已经过去了，请换个时间再提交。")
    if end <= start:
        end = start + timedelta(hours=8)
    tonnage = _as_float(slots["tonnage"])

    summary = (
        f"提交派车申请：{_fmt_dt(start)} 从 {slots['start_address']} 装货 "
        f"到 {slots['end_address']} 卸货"
    )
    if slots["cargo"]:
        summary += f"，{slots['cargo']}"
    if tonnage:
        summary += f" {tonnage:g} 吨"
    if slots["project"]:
        summary += f"，项目 {slots['project']}"
    if slots["reason"]:
        summary += f"，事由 {slots['reason']}"
    params = {
        "start_address": slots["start_address"],
        "end_address": slots["end_address"],
        "start_time": start.strftime("%Y-%m-%d %H:%M"),
        "end_time": end.strftime("%Y-%m-%d %H:%M"),
        "cargo": slots["cargo"],
        "tonnage": tonnage,
        "project": slots["project"],
        "reason": slots["reason"],
    }
    return _confirm(
        db,
        principal,
        session_id,
        action="vehicle.create_application",
        params=params,
        summary=summary,
        prompt=f"将{summary}，确认提交吗？",
    )


def _handle_approve(
    db: Session, principal: Principal, text: str, session_id: str | None
) -> dict[str, Any]:
    match = CAR_NO_RE.search(text.upper())
    if not match:
        return _reply("请提供派车申请单号，例如：批准派车申请 CA202611160001，派车 渝B12345。")
    application_no = match.group(0)
    decision = "reject" if any(word in text for word in ("驳回", "不同意")) else "approve"
    comment: str | None = None
    if decision == "reject":
        marker = "驳回" if "驳回" in text else "不同意"
        tail = text.split(marker, 1)[1]
        tail = CAR_NO_RE.sub("", tail)
        comment = re.sub(r"^(?:申请|单号)?[：:，,。\s]+", "", tail.strip()).strip() or None
        if not comment:
            return _reply(
                f"驳回需要填写原因，例如：驳回派车申请 {application_no}，原因：车辆已排满。"
            )

    try:
        require_permission(principal, "car_application", "approve")
        row = vehicle_service.get_application(db, principal, application_no)
    except AppError as exc:
        return _reply(exc.message)
    if row.status != "pending":
        label = vehicle_service.APPLICATION_STATUS_LABELS.get(row.status, row.status)
        return _reply(f"申请 {application_no} 当前是{label}，不需要再审批。")

    plate_match = PLATE_RE.search(text.upper())
    plate_no = plate_match.group(0) if plate_match else None
    summary = (
        f"审批派车申请 {application_no}（{row.applicant_name}，"
        f"{_fmt_dt(row.start_time)} {row.start_address} → {row.end_address}）："
    )
    if decision == "approve":
        summary += "批准" + (f"，派车 {plate_no}" if plate_no else "")
    else:
        summary += f"驳回，原因：{comment}"
    return _confirm(
        db,
        principal,
        session_id,
        action="vehicle.approve_application",
        params={
            "application_no": application_no,
            "decision": decision,
            "comment": comment,
            "plate_no": plate_no,
        },
        summary=summary,
        prompt=f"将{summary}，确认执行吗？",
    )


def _handle_vehicles(principal: Principal, text: str) -> dict[str, Any]:
    status = None
    if any(word in text for word in ("可派", "空闲", "可用")):
        status = "available"
    elif "维修" in text or "保养" in text:
        status = "maintenance"
    elif "使用中" in text or "在用" in text:
        status = "in_use"
    elif "停用" in text:
        status = "disabled"
    plate_match = PLATE_RE.search(text.upper())
    args: dict[str, Any] = {"page_size": 20}
    if status:
        args["status"] = status
    if plate_match:
        args["keyword"] = plate_match.group(0)
    ok, data, message = _tool("vehicle.list", args, principal)
    if not ok:
        return _reply(message or "查询车辆失败。")
    items = data.get("items") or []
    if not items:
        return _reply("没有查到符合条件的车辆。")
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status_label"]] = counts.get(item["status_label"], 0) + 1
    head = "，".join(f"{label} {count} 台" for label, count in counts.items())
    lines = [f"共 {data['total']} 台车：{head}"]
    for item in items[:12]:
        driver = f"，司机 {item['driver_name']}" if item["driver_name"] else ""
        trailer = f"，挂车 {item['trailer_no']}" if item["trailer_no"] else ""
        lines.append(
            f"· {item['plate_no']} {item['model'] or ''}"
            f"（{item['vehicle_type_label']}，载重 {item['load_ton']} 吨{trailer}{driver}）："
            f"{item['status_label']}，里程 {item['mileage_km']} km"
        )
    return _reply("\n".join(lines), sources=[{"type": "vehicle", "name": "vehicle_list"}])


def _handle_stats(
    principal: Principal,
    text: str,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    group_by = "car"
    if "项目" in text:
        group_by = "project"
    elif "部门" in text or "单位" in text:
        group_by = "dept"
    elif "每月" in text or "趋势" in text or "月度" in text:
        group_by = "month"
    start, end = _date_range(text, start_date, end_date)
    args: dict[str, Any] = {"group_by": group_by}
    if start:
        args["start_date"] = start.isoformat()
    if end:
        args["end_date"] = end.isoformat()
    ok, data, message = _tool("vehicle.usage_stats", args, principal)
    if not ok:
        return _reply(message or "查询发运统计失败。")
    summary = data["summary"]
    if int(summary["trips"]) == 0:
        return _reply(f"{_period_label(start, end)}没有已完成的发运记录。")
    label = {"car": "按车辆", "project": "按项目", "dept": "按部门", "month": "按月份"}[group_by]
    lines = [
        f"{_period_label(start, end)}共发运 {summary['trips']} 车次，"
        f"载货 {summary['tonnage']} 吨，总里程 {summary['mileage_km']} km，"
        f"总费用 {summary['total_cost']} 元"
        f"（油费 {summary['fuel_cost']}、通行费 {summary['toll_fee']}、"
        f"停车费 {summary['parking_fee']}、其他 {summary['other_fee']}）。",
        f"{label}：",
    ]
    for item in data["groups"][:10]:
        lines.append(
            f"· {item['name']}：{item['trips']} 车次，{item['mileage_km']} km，"
            f"费用 {item['total_cost']} 元"
        )
    return _reply("\n".join(lines), sources=[{"type": "vehicle", "name": "usage_stats"}])


def _report_context(data: dict[str, Any], start: date | None, end: date | None) -> str:
    summary = data["summary"]
    lines = [
        f"统计区间：{_period_label(start, end)}",
        f"总览：发运 {summary['trips']} 车次，载货 {summary['tonnage']} 吨，"
        f"总里程 {summary['mileage_km']} km，"
        f"总费用 {summary['total_cost']} 元（油费 {summary['fuel_cost']}，"
        f"通行费 {summary['toll_fee']}，停车费 {summary['parking_fee']}，"
        f"其他 {summary['other_fee']}）",
        "车队台数：" + "，".join(f"{k} {v} 台" for k, v in data["vehicle_status"].items()),
        "按车辆：",
    ]
    for item in data["by_car"]:
        lines.append(
            f"- {item['name']}：{item['trips']} 车次，{item['mileage_km']} km，"
            f"{item['total_cost']} 元"
        )
    for title, key in (("按项目", "by_project"), ("按部门", "by_dept"), ("按月", "by_month")):
        rows = data[key]
        if not rows:
            continue
        lines.append(f"{title}：")
        for item in rows:
            lines.append(
                f"- {item['name']}：{item['trips']} 车次，{item['mileage_km']} km，"
                f"{item['total_cost']} 元"
            )
    return "\n".join(lines)


def _fallback_report(
    data: dict[str, Any], start: date | None, end: date | None
) -> str:
    summary = data["summary"]
    lines = [
        f"{_period_label(start, end)}半挂车队运输报告",
        f"共发运 {summary['trips']} 车次，载货 {summary['tonnage']} 吨，"
        f"总里程 {summary['mileage_km']} km，总费用 {summary['total_cost']} 元。",
    ]
    by_car = data["by_car"]
    if by_car:
        top_cost = by_car[0]
        lines.append(
            f"· 费用最高：{top_cost['name']}，{top_cost['trips']} 车次，"
            f"{top_cost['mileage_km']} km，{top_cost['total_cost']} 元"
        )
        top_trips = max(by_car, key=lambda item: item["trips"])
        lines.append(f"· 发运最多：{top_trips['name']}，{top_trips['trips']} 车次")
    if data["by_project"]:
        share = data["by_project"][0]
        lines.append(f"· 派车最多项目：{share['name']}，{share['trips']} 车次")
    if data["by_dept"]:
        dept = data["by_dept"][0]
        lines.append(f"· 派车最多部门：{dept['name']}，{dept['trips']} 车次")
    lines.append("· 建议：优先安排回程配货，减少空驶里程。")
    return "\n".join(lines)


def _handle_report(
    principal: Principal,
    text: str,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    start, end = _date_range(text, start_date, end_date)
    args: dict[str, Any] = {}
    if start:
        args["start_date"] = start.isoformat()
    if end:
        args["end_date"] = end.isoformat()
    ok, data, message = _tool("vehicle.report_data", args, principal)
    if not ok:
        return _reply(message or "获取发运数据失败。")
    if int(data["summary"]["trips"]) == 0:
        return _reply(f"{_period_label(start, end)}没有已完成的发运记录，暂时写不了报告。")
    context = _report_context(data, start, end)
    try:
        answer = llm.generate("vehicle_report.v1.md", context)
    except llm.LLMError:
        answer = _fallback_report(data, start, end)
    return _reply(answer, sources=[{"type": "vehicle", "name": "report"}])


def _short_dt(value: Any) -> str:
    """把接口返回的 ISO 时间显示成“11月17日 09:00”。"""
    parsed = _parse_datetime(value)
    return _fmt_dt(parsed) if parsed else str(value or "-")


def _handle_applications(principal: Principal, text: str) -> dict[str, Any]:
    args: dict[str, Any] = {"page_size": 10}
    if "待审批" in text or "没审批" in text:
        args["status"] = "pending"
    elif "已批准" in text or "通过" in text:
        args["status"] = "approved"
    elif "已驳回" in text or "驳回" in text:
        args["status"] = "rejected"
    elif "已完成" in text:
        args["status"] = "completed"
    match = CAR_NO_RE.search(text.upper())
    if match:
        args["keyword"] = match.group(0)
    start, end = _date_range(text)
    if start:
        args["start_date"] = start.isoformat()
    if end:
        args["end_date"] = end.isoformat()
    ok, data, message = _tool("vehicle.application_list", args, principal)
    if not ok:
        return _reply(message or "查询派车申请失败。")
    items = data.get("items") or []
    if not items:
        return _reply("没有查到符合条件的派车申请。")
    lines = [f"共 {data['total']} 条派车申请，显示最近 {len(items)} 条："]
    for item in items:
        plate = f"，派车 {item['plate_no']}" if item["plate_no"] else ""
        cargo = f"，{item['cargo']}" if item["cargo"] else ""
        lines.append(
            f"· {item['application_no']}（{item['applicant_name']}）{item['status_label']}："
            f"{_short_dt(item['start_time'])} {item['start_address']} → {item['end_address']}"
            f"{cargo} {item['tonnage']} 吨{plate}"
        )
    return _reply("\n".join(lines), sources=[{"type": "vehicle", "name": "applications"}])


HELP_TEXT = (
    "半挂车队可以这样问：\n"
    "· 查车：现在有哪些半挂车能派？/ 渝B12345 是谁在开？\n"
    "· 要数据：本月发运多少车次、载了多少吨、跑了多少公里、花了多少钱？\n"
    "· 写报告：写一份上个月车队运输报告\n"
    "· 提申请：明天上午9点从打通煤矿到珞璜电厂，拉32吨精煤，申请派车\n"
    "· 审批：批准派车申请 CA202611160001，派车 渝B12345"
)


def run(
    db: Session,
    principal: Principal,
    question: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    text = question.strip()
    try:
        if any(
            word in text
            for word in (
                "买车",
                "购车",
                "购置",
                "想买",
                "要买",
                "买一台",
                "买一辆",
                "价位",
                "报价",
                "多少钱一台",
                "推荐一款",
                "推荐一台",
                "哪个牌子",
                "什么牌子",
                "二手",
            )
        ):
            return _reply(
                "车辆购置、车型推荐和价格咨询不在系统范围内。"
                "这里能办的是公司现有半挂车队的事：查车辆状态、发运统计、运输报告、提派车申请。"
            )
        if any(word in text for word in REPORT_WORDS):
            return _handle_report(principal, text, start_date, end_date)
        if CAR_NO_RE.search(text.upper()) and any(
            word in text for word in APPROVE_WORDS
        ):
            return _handle_approve(db, principal, text, session_id)
        if any(word in text for word in CREATE_WORDS) and not any(
            word in text
            for word in ("查", "看", "记录", "列表", "审批", "驳回", "我的", "待审批", "有哪些")
        ) and not any(word in text for word in REPORT_WORDS):
            return _handle_create(db, principal, text, session_id)
        if any(word in text for word in STATS_WORDS):
            return _handle_stats(principal, text, start_date, end_date)
        if any(word in text for word in LIST_WORDS):
            return _handle_applications(principal, text)
        if any(word in text for word in VEHICLE_WORDS) or PLATE_RE.search(text.upper()):
            return _handle_vehicles(principal, text)
        return _reply(HELP_TEXT)
    except AppError as exc:
        return _reply(exc.message)
