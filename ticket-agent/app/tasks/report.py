"""V3 定时报告任务：独立 report 队列，失败重试 3 次后通知。"""

from __future__ import annotations

from datetime import date

from app.core.db import SessionLocal
from app.core.logging import logger
from app.services import report_service
from app.tasks.celery_app import celery_app
from app.tasks.common import log_task, retry_delay


@celery_app.task(bind=True, name="generate_report", max_retries=3, soft_time_limit=300)
def generate_report(
    self, report_type: str, period_start: str | None = None, period_end: str | None = None
) -> dict[str, str | int | None]:
    start = date.fromisoformat(period_start) if period_start else None
    end = date.fromisoformat(period_end) if period_end else None
    with SessionLocal() as db:
        try:
            report, created = report_service.generate(
                db, report_type, period_start=start, period_end=end
            )
            logger.info(
                "report_generated",
                extra={"report_id": report.id, "report_type": report_type, "created": created},
            )
            return {"report_id": report.id, "status": report.status, "created": int(created)}
        except Exception as exc:
            failed = report_service.find_report(db, report_type, start, end)
            if failed is not None:
                report_service.mark_failed(db, failed, str(exc))
                if self.request.retries >= self.max_retries:
                    report_service.notify_failure(db, failed)
                    db.commit()
                logger.error(
                    "report_generate_failed",
                    extra={
                        "report_id": failed.id,
                        "report_type": report_type,
                        "error": str(exc)[:500],
                        "retry_count": self.request.retries,
                    },
                )
            log_task(
                db,
                action="generate_report",
                result="failure",
                detail={
                    "report_type": report_type,
                    "error": str(exc)[:500],
                    "retry_count": self.request.retries,
                },
            )
            db.commit()
            raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc
