"""Celery 应用：Redis db1 作 broker、db2 作 backend，调度时区 Asia/Shanghai。"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings


def _with_db(url: str, db: int) -> str:
    base, sep, last = url.rpartition("/")
    if not sep or not last.isdigit():
        return url
    return f"{base}/{db}"


celery_app = Celery(
    "ticket_agent",
    broker=_with_db(settings.redis_url, 1),
    backend=_with_db(settings.redis_url, 2),
    include=[
        "app.tasks.overdue",
        "app.tasks.cleanup",
        "app.tasks.document",
        "app.tasks.report",
        "app.tasks.alert",
    ],
)

celery_app.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_default_queue="default",
    task_routes={"generate_report": {"queue": "report"}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=600,
    task_soft_time_limit=570,
    broker_connection_retry_on_startup=True,
)
