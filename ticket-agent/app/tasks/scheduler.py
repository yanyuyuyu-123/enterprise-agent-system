"""APScheduler 独立进程入口：只做定时触发，耗时逻辑在 Celery task。"""

from __future__ import annotations

from functools import partial

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.db import SessionLocal
from app.services.setting_service import get_int
from app.tasks.alert import scan_alerts
from app.tasks.cleanup import (
    archive_operation_logs,
    cleanup_agent_logs,
    cleanup_system_logs,
    cleanup_voice_files,
)
from app.tasks.overdue import mark_overdue_orders
from app.tasks.report import generate_report

TIMEZONE = "Asia/Shanghai"


def _settings() -> tuple[int, int, int]:
    with SessionLocal() as db:
        return (
            get_int(db, "alert.scan.interval_minutes", 60),
            get_int(db, "report.schedule.hour", 8),
            get_int(db, "report.schedule.minute", 0),
        )


def _dispatch_report(report_type: str) -> None:
    generate_report.apply_async(args=[report_type], queue="report")


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    common = {"replace_existing": True, "coalesce": True, "max_instances": 1}
    interval_minutes, report_hour, report_minute = _settings()

    scheduler.add_job(
        mark_overdue_orders.apply,
        CronTrigger(minute="*/5", timezone=TIMEZONE),
        id="mark_overdue_orders",
        **common,
    )
    scheduler.add_job(
        scan_alerts.apply,
        IntervalTrigger(minutes=interval_minutes, timezone=TIMEZONE),
        id="scan_alerts",
        **common,
    )
    for report_type, trigger in (
        ("daily", CronTrigger(hour=report_hour, minute=report_minute, timezone=TIMEZONE)),
        (
            "weekly",
            CronTrigger(
                day_of_week="mon", hour=report_hour, minute=report_minute, timezone=TIMEZONE
            ),
        ),
        (
            "monthly",
            CronTrigger(day=1, hour=report_hour, minute=report_minute, timezone=TIMEZONE),
        ),
        (
            "yearly",
            CronTrigger(month=1, day=1, hour=report_hour, minute=report_minute, timezone=TIMEZONE),
        ),
    ):
        scheduler.add_job(
            partial(_dispatch_report, report_type),
            trigger,
            id=f"report_{report_type}",
            **common,
        )
    scheduler.add_job(
        cleanup_agent_logs.apply,
        CronTrigger(hour=3, minute=30, timezone=TIMEZONE),
        id="cleanup_agent_logs",
        **common,
    )
    scheduler.add_job(
        cleanup_system_logs.apply,
        CronTrigger(hour=3, minute=30, timezone=TIMEZONE),
        id="cleanup_system_logs",
        **common,
    )
    scheduler.add_job(
        cleanup_voice_files.apply,
        CronTrigger(hour=4, minute=0, timezone=TIMEZONE),
        id="cleanup_voice_files",
        **common,
    )
    scheduler.add_job(
        archive_operation_logs.apply,
        CronTrigger(day=1, hour=3, minute=0, timezone=TIMEZONE),
        id="archive_operation_logs",
        **common,
    )
    return scheduler


def main() -> None:
    scheduler = build_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
