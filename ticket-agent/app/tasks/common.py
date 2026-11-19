"""定时任务共用：系统账号、失败重试间隔、系统日志。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import User
from app.services.log_service import write_log_safely

# 失败重试间隔（秒）：10s/60s/300s，最多 3 次
RETRY_DELAYS: tuple[int, ...] = (10, 60, 300)


def retry_delay(retries: int) -> int:
    return RETRY_DELAYS[min(retries, len(RETRY_DELAYS) - 1)]


def system_user_id(db: Session) -> int | None:
    """定时任务以 is_system 账号运行；未种系统账号时返回 None。"""
    return db.scalar(select(User.id).where(User.is_system.is_(True)).limit(1))


def log_task(
    db: Session,
    *,
    action: str,
    result: str = "success",
    detail: dict[str, Any] | None = None,
) -> None:
    write_log_safely(
        db,
        log_type="system",
        resource="task",
        action=action,
        user_id=system_user_id(db),
        user_name="系统",
        result=result,
        detail=detail,
    )
