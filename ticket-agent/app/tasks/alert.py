"""V3 异常预警定时扫描：每轮独立事务，失败重试 2 次。"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.core.logging import logger
from app.services import alert_service
from app.tasks.celery_app import celery_app
from app.tasks.common import log_task, retry_delay


@celery_app.task(bind=True, name="scan_alerts", max_retries=2, soft_time_limit=600)
def scan_alerts(self) -> dict[str, int]:
    with SessionLocal() as db:
        try:
            result = alert_service.scan(db)
            logger.info("alert_scan_done", extra={"result": result})
            return result
        except Exception as exc:
            log_task(
                db,
                action="scan_alerts",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
            raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc
