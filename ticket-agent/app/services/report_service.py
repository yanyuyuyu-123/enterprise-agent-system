"""报告中心：定时汇总工单、业务、财务与预警数据，渲染静态 HTML 存档。"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import SCOPE_COMPANY
from app.core.errors import AppError
from app.core.storage import get_storage
from app.models.alert import Alert
from app.models.business import FinanceRecord
from app.models.misc import Notification
from app.models.org import User
from app.models.report import Report, ReportViewer
from app.models.work_order import WorkOrder
from app.services import metric_service, stats_service
from app.services.log_service import write_log_safely
from app.services.notification_service import notify
from app.services.permission_service import Permission, Principal, has_permission
from app.services.recipients import user_ids_by_positions

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_TYPES: dict[str, str] = {
    "daily": "经营日报",
    "weekly": "经营周报",
    "monthly": "经营月报",
    "yearly": "经营年报",
}
CATEGORY_LABELS: dict[str, str] = {
    "device_repair": "设备维修",
    "expense_reimbursement": "报销",
    "security_patrol": "安全巡查",
    "transport_exception": "运输异常",
}
STATUS_LABELS: dict[str, str] = {
    "supplementing": "补充信息",
    "pending_assignment": "待分配",
    "pending_process": "待处理",
    "processing": "处理中",
    "pending_review": "待审核",
    "rejected": "已驳回",
    "completed": "已完成",
    "cancelled": "已取消",
}
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

# 系统任务没有登录用户，固定按全公司范围取数
SYSTEM_PRINCIPAL = Principal(
    user_id=0,
    employee_no="system",
    name="系统",
    department_id=None,
    position_codes=frozenset(),
    permissions=(
        Permission("report", "read", SCOPE_COMPANY),
        Permission("work_order", "read", SCOPE_COMPANY),
    ),
)


def _month_range(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return start, end


def default_period(
    report_type: str, now: datetime | None = None
) -> tuple[date, date, date | None, date | None]:
    """返回 (统计开始, 统计结束, 对比开始, 对比结束)。"""
    today = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI).date()
    if report_type == "daily":
        end = today - timedelta(days=1)
        return end, end, end - timedelta(days=1), end - timedelta(days=1)
    if report_type == "weekly":
        monday = today - timedelta(days=today.weekday())
        end = monday - timedelta(days=1)
        start = end - timedelta(days=6)
        return start, end, start - timedelta(days=7), end - timedelta(days=7)
    if report_type == "monthly":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        compare_end = start - timedelta(days=1)
        compare_start, _ = _month_range(compare_end)
        return start, end, compare_start, compare_end
    if report_type == "yearly":
        end = date(today.year - 1, 12, 31)
        start = date(today.year - 1, 1, 1)
        return start, end, date(today.year - 2, 1, 1), date(today.year - 2, 12, 31)
    raise AppError(1003, "报告类型不存在", 400)


def _utc_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    begin = datetime.combine(start, time.min, tzinfo=SHANGHAI).astimezone(UTC)
    finish = datetime.combine(end + timedelta(days=1), time.min, tzinfo=SHANGHAI).astimezone(UTC)
    return begin, finish - timedelta(microseconds=1)


def _next_report_no(db: Session, period_end: date) -> str:
    prefix = f"RP{period_end:%Y%m%d}"
    count = db.scalar(select(func.count(Report.id)).where(Report.report_no.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:03d}"


def _alerts_summary(db: Session, start: date, end: date) -> dict[str, int]:
    begin, finish = _utc_bounds(start, end)
    rows = db.execute(
        select(Alert.level, func.count())
        .where(Alert.triggered_at >= begin, Alert.triggered_at <= finish)
        .group_by(Alert.level)
    ).all()
    result = {"critical": 0, "warning": 0, "info": 0}
    for level, count in rows:
        result[level] = count
    return result


def _has_mock(db: Session, start: date, end: date) -> bool:
    begin, finish = _utc_bounds(start, end)
    if db.scalar(
        select(WorkOrder.id)
        .where(
            WorkOrder.is_mock.is_(True),
            WorkOrder.created_at >= begin,
            WorkOrder.created_at <= finish,
        )
        .limit(1)
    ):
        return True
    if db.scalar(
        select(FinanceRecord.id)
        .where(
            FinanceRecord.is_mock.is_(True),
            FinanceRecord.record_date >= start,
            FinanceRecord.record_date <= end,
        )
        .limit(1)
    ):
        return True
    return bool(
        db.scalar(
            select(Alert.id)
            .where(
                Alert.is_mock.is_(True),
                Alert.triggered_at >= begin,
                Alert.triggered_at <= finish,
            )
            .limit(1)
        )
    )


def _delta_text(current: Any, previous: Any, *, unit: str = "") -> str:
    if current is None or previous is None:
        return "无数据"
    diff = Decimal(str(current)) - Decimal(str(previous))
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff}{unit}"


def _conclusions(
    work_orders: dict[str, Any],
    finance: dict[str, Any],
    alerts: dict[str, int],
    margin_delta: Any,
) -> list[str]:
    lines: list[str] = []
    rate = work_orders.get("completion_rate")
    if rate is None:
        lines.append("区间内无工单，工单完成率无法计算。")
    elif rate >= 0.9:
        lines.append(f"工单完成率 {rate:.2%}，处理效率良好。")
    elif rate >= 0.7:
        lines.append(f"工单完成率 {rate:.2%}，处于正常区间，仍有提升空间。")
    else:
        lines.append(f"工单完成率 {rate:.2%}，偏低，建议排查积压与分配效率。")

    overdue = int(work_orders.get("overdue") or 0)
    if overdue:
        lines.append(f"超时工单 {overdue} 件，建议优先处理。")
    else:
        lines.append("本区间无超时工单。")

    if margin_delta is not None:
        direction = "上升" if margin_delta >= 0 else "下降"
        lines.append(f"毛利率较上一对比区间{direction} {abs(float(margin_delta)):.2f} 个百分点。")

    if alerts["critical"]:
        lines.append(f"存在 {alerts['critical']} 条严重预警，需尽快处置。")
    if finance.get("gross_margin_note"):
        lines.append(f"毛利率：{finance['gross_margin_note']}，请人工核实收入数据。")
    lines.append("市场分析：无数据来源。")
    return lines


def _render(report: Report, context: dict[str, Any], *, is_mock: bool) -> bytes:
    template = _ENV.get_template("report.html")
    html = template.render(
        report=report,
        type_label=REPORT_TYPES[report.report_type],
        is_mock=is_mock,
        **context,
    )
    return html.encode("utf-8")


def _context(
    db: Session, *, report_type: str, start: date, end: date, compare: tuple[date, date] | None
) -> dict[str, Any]:
    begin, finish = _utc_bounds(start, end)
    work_orders = stats_service.work_order_stats(
        db, SYSTEM_PRINCIPAL, start_at=begin, end_at=finish
    )
    category_rows = [
        {"label": CATEGORY_LABELS.get(category, category), "count": count}
        for category, count in work_orders["by_category"].items()
    ]
    status_rows = [
        {"label": STATUS_LABELS.get(status, status), "count": count}
        for status, count in work_orders["by_status"].items()
    ]

    sales = metric_service.sales_summary(db, start, end)
    purchase = metric_service.purchase_summary(db, start, end)
    inventory = metric_service.inventory_summary(db, start, end)
    finance = metric_service.finance_summary(db, start, end)
    alerts = _alerts_summary(db, start, end)

    trend = None
    compare_values: dict[str, Any] = {
        "work_orders_total": "无数据",
        "work_orders_delta": "无数据",
        "sales_amount": "无数据",
        "sales_delta": "无数据",
        "gross_margin": "无数据",
        "margin_delta": "无数据",
    }
    margin_delta: Any = None
    if report_type != "daily":
        trend = stats_service.work_order_trend(
            db,
            SYSTEM_PRINCIPAL,
            start_at=begin,
            end_at=finish,
            granularity={"weekly": "day", "monthly": "day", "yearly": "month"}[report_type],
        )
        if compare is not None:
            c_begin, c_finish = _utc_bounds(*compare)
            compare_stats = stats_service.work_order_stats(
                db, SYSTEM_PRINCIPAL, start_at=c_begin, end_at=c_finish
            )
            compare_sales = metric_service.sales_summary(db, *compare)
            compare_finance = metric_service.finance_summary(db, *compare)
            compare_values["work_orders_total"] = f"{compare_stats['total']} 件"
            compare_values["work_orders_delta"] = _delta_text(
                work_orders["total"], compare_stats["total"], unit=" 件"
            )
            compare_values["sales_amount"] = f"{compare_sales['sales_amount']} 元"
            compare_values["sales_delta"] = _delta_text(
                Decimal(sales["sales_amount"]), Decimal(compare_sales["sales_amount"]), unit=" 元"
            )
            compare_values["gross_margin"] = (
                f"{compare_finance['gross_margin']}%"
                if compare_finance["gross_margin"] is not None
                else "无数据"
            )
            if finance["gross_margin"] is not None and compare_finance["gross_margin"] is not None:
                margin_delta = round(
                    float(finance["gross_margin"]) - float(compare_finance["gross_margin"]), 2
                )
                compare_values["margin_delta"] = _delta_text(
                    finance["gross_margin"], compare_finance["gross_margin"], unit=" 个百分点"
                )
            else:
                compare_values["margin_delta"] = "无数据"

    return {
        "work_orders": work_orders,
        "category_rows": category_rows,
        "status_rows": status_rows,
        "sales": sales,
        "purchase": purchase,
        "inventory": inventory,
        "finance": finance,
        "alerts": alerts,
        "trend": trend,
        "compare": compare_values,
        "sources": {
            "sales_summary": "销售订单.xlsx-第 1 页",
            "purchase_summary": "采购订单.xlsx-第 1 页",
            "inventory_summary": "库存台账.xlsx-第 1 页",
            "finance_summary": "财务报表.xlsx-第 1 页",
        },
        "conclusions": _conclusions(work_orders, finance, alerts, margin_delta),
    }


def generate(
    db: Session,
    report_type: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[Report, bool]:
    """生成或复用报告；返回 (报告, 是否新建)。仅定时任务调用。"""
    if report_type not in REPORT_TYPES:
        raise AppError(1003, "报告类型不存在", 400)
    default_start, default_end, compare_start, compare_end = default_period(report_type)
    start = period_start or default_start
    end = period_end or default_end
    if start > end:
        raise AppError(1003, "开始日期不能晚于结束日期", 400)
    if end >= datetime.now(SHANGHAI).date():
        raise AppError(3000, "统计区间未结束，不能生成报告", 400)
    if period_start is not None or period_end is not None:
        # 手工指定区间时不做同环比，避免对比区间与统计区间错位
        compare_start, compare_end = None, None

    existing = db.scalar(
        select(Report).where(
            Report.report_type == report_type,
            Report.period_start == start,
            Report.period_end == end,
        )
    )
    if existing is not None and existing.status == "generated":
        return existing, False

    report = existing or Report(
        report_no=_next_report_no(db, end),
        report_type=report_type,
        period_start=start,
        period_end=end,
    )
    report.compare_start = compare_start
    report.compare_end = compare_end
    report.status = "generating"
    report.error_message = None
    if existing is None:
        db.add(report)
    db.commit()

    try:
        context = _context(
            db,
            report_type=report_type,
            start=start,
            end=end,
            compare=(compare_start, compare_end) if compare_start and compare_end else None,
        )
        is_mock = _has_mock(db, start, end)
        content = _render(report, context, is_mock=is_mock)
        relative = f"reports/{report.report_no}.html"
        get_storage().save(relative, content)
        report.file_path = relative
        report.file_size = len(content)
        report.status = "generated"
        report.generated_at = datetime.now(UTC)
        report.is_mock = is_mock
        db.commit()
        notify_published(db, report)
        write_log_safely(
            db,
            log_type="system",
            resource="report",
            action="generate",
            user_name="系统",
            target_type="report",
            target_id=report.id,
            detail={
                "report_no": report.report_no,
                "report_type": report_type,
                "period_start": str(start),
                "period_end": str(end),
                "status": report.status,
                "is_mock": is_mock,
            },
        )
        db.commit()
        return report, True
    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)[:500]
        db.commit()
        raise


def find_report(
    db: Session, report_type: str, start: date | None, end: date | None
) -> Report | None:
    """供任务失败时定位报告行；未指定区间时用默认区间。"""
    if start is None or end is None:
        default_start, default_end, _, _ = default_period(report_type)
        start = start or default_start
        end = end or default_end
    return db.scalar(
        select(Report).where(
            Report.report_type == report_type,
            Report.period_start == start,
            Report.period_end == end,
        )
    )


def mark_failed(db: Session, report: Report, message: str) -> None:
    report.status = "failed"
    report.error_message = message[:500]
    db.commit()


def notify_published(db: Session, report: Report) -> None:
    """同日多份报告合并为一条通知。"""
    recipients = set(user_ids_by_positions(db, "general_manager"))
    recipients.update(db.scalars(select(ReportViewer.user_id)).all())
    if not recipients:
        return
    day_start = datetime.combine(
        datetime.now(SHANGHAI).date(), time.min, tzinfo=SHANGHAI
    ).astimezone(UTC)
    title = f"{REPORT_TYPES[report.report_type]}已生成"
    if report.is_mock:
        title = f"[模拟数据] {title}"
    for user_id in sorted(recipients):
        already = db.scalar(
            select(Notification.id)
            .where(
                Notification.user_id == user_id,
                Notification.type == "report_published",
                Notification.created_at >= day_start,
            )
            .limit(1)
        )
        if already:
            continue
        notify(
            db,
            user_id=user_id,
            type="report_published",
            title=title,
            content=f"{report.report_no}（{report.period_start} 至 {report.period_end}）",
            related_id=report.id,
            related_type="report",
        )


def notify_failure(db: Session, report: Report) -> None:
    for user_id in set(user_ids_by_positions(db, "general_manager", "hr_head")):
        notify(
            db,
            user_id=user_id,
            type="system",
            title="报告生成失败",
            content=f"{report.report_no} 生成失败：{report.error_message or '未知原因'}",
            related_id=report.id,
            related_type="report",
        )


def _scope(db: Session, principal: Principal) -> bool:
    """report:read 或名单命中；名单用户只读。"""
    if has_permission(principal, "report", "read"):
        return True
    return (
        db.scalar(select(ReportViewer.id).where(ReportViewer.user_id == principal.user_id))
        is not None
    )


def list_reports(
    db: Session,
    principal: Principal,
    *,
    report_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if not _scope(db, principal):
        raise AppError(2001, "无该资源权限", 403)
    if page < 1 or page_size < 1 or page_size > 100:
        raise AppError(1003, "分页参数非法", 400)
    conditions = [Report.status == "generated"]
    if report_type:
        if report_type not in REPORT_TYPES:
            raise AppError(1003, "报告类型不存在", 400)
        conditions.append(Report.report_type == report_type)
    if start_date:
        conditions.append(Report.period_start >= start_date)
    if end_date:
        conditions.append(Report.period_end <= end_date)

    total = db.scalar(select(func.count(Report.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Report)
        .where(*conditions)
        .order_by(Report.period_end.desc(), Report.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_payload(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _payload(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "report_no": report.report_no,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "compare_start": report.compare_start.isoformat() if report.compare_start else None,
        "compare_end": report.compare_end.isoformat() if report.compare_end else None,
        "status": report.status,
        "file_size": report.file_size,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "is_mock": report.is_mock,
    }


def get_report(db: Session, principal: Principal, report_id: int) -> dict[str, Any]:
    if not _scope(db, principal):
        raise AppError(2001, "无该资源权限", 403)
    report = db.get(Report, report_id)
    if report is None or report.status != "generated" or not report.file_path:
        raise AppError(3003, "报告不存在", 404)
    content = get_storage().read(report.file_path).decode("utf-8")
    write_log_safely(
        db,
        resource="report",
        action="read",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        target_type="report",
        target_id=report.id,
        detail={"report_no": report.report_no, "report_type": report.report_type},
    )
    db.commit()
    return {**_payload(report), "content": content}


def get_report_file(db: Session, principal: Principal, report_id: int) -> tuple[Report, bytes]:
    if not _scope(db, principal):
        raise AppError(2001, "无该资源权限", 403)
    report = db.get(Report, report_id)
    if report is None or report.status != "generated" or not report.file_path:
        raise AppError(3003, "报告不存在", 404)
    return report, get_storage().read(report.file_path)


def list_viewers(db: Session, principal: Principal) -> dict[str, Any]:
    if not principal.has_position("general_manager"):
        raise AppError(2001, "仅总经理可维护报告查看名单", 403)
    rows = db.execute(
        select(ReportViewer, User.name, User.employee_no)
        .join(User, User.id == ReportViewer.user_id)
        .order_by(ReportViewer.id)
    ).all()
    return {
        "items": [
            {
                "user_id": row.ReportViewer.user_id,
                "name": row.name,
                "employee_no": row.employee_no,
                "granted_at": row.ReportViewer.created_at.isoformat(),
            }
            for row in rows
        ]
    }


def list_viewer_candidates(db: Session, principal: Principal) -> dict[str, Any]:
    if not principal.has_position("general_manager"):
        raise AppError(2001, "仅总经理可维护报告查看名单", 403)
    rows = db.execute(
        select(User.id, User.name, User.employee_no, User.department_id)
        .where(User.deleted_at.is_(None), User.status == "active")
        .order_by(User.id)
    ).all()
    return {
        "items": [
            {
                "user_id": row.id,
                "name": row.name,
                "employee_no": row.employee_no,
                "department_id": row.department_id,
            }
            for row in rows
        ]
    }


def update_viewers(db: Session, principal: Principal, user_ids: list[int]) -> dict[str, Any]:
    if not principal.has_position("general_manager"):
        raise AppError(2001, "仅总经理可维护报告查看名单", 403)
    if len(set(user_ids)) != len(user_ids):
        raise AppError(1003, "名单存在重复用户", 400)
    if user_ids:
        existing_users = set(
            db.scalars(
                select(User.id).where(User.id.in_(user_ids), User.deleted_at.is_(None))
            ).all()
        )
        missing = sorted(set(user_ids) - existing_users)
        if missing:
            raise AppError(1003, f"用户不存在：{missing}", 400)

    current = set(db.scalars(select(ReportViewer.user_id)).all())
    target = set(user_ids)
    for row in db.scalars(
        select(ReportViewer).where(ReportViewer.user_id.in_(current - target))
    ).all():
        db.delete(row)
    for user_id in sorted(target - current):
        db.add(ReportViewer(user_id=user_id, granted_by=principal.user_id))
    write_log_safely(
        db,
        resource="report",
        action="update_viewers",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        log_level="critical",
        target_type="report_viewer",
        detail={"added": sorted(target - current), "removed": sorted(current - target)},
    )
    db.commit()
    return list_viewers(db, principal)
