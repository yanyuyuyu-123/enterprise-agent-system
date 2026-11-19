"""知识文档解析任务：document 队列，失败按 10s/60s/300s 退避重试。"""

from __future__ import annotations

from app.services import ingest_service
from app.tasks.celery_app import celery_app

RETRY_DELAYS = (10, 60, 300)


@celery_app.task(bind=True, name="knowledge.parse_document", queue="document", max_retries=3)
def parse_knowledge_document(self, document_id: int, version: int) -> None:
    try:
        ingest_service.parse_document(document_id, version)
    except Exception as exc:  # noqa: BLE001 - 交给 Celery 重试
        if self.request.retries >= len(RETRY_DELAYS):
            return
        raise self.retry(exc=exc, countdown=RETRY_DELAYS[self.request.retries]) from exc
