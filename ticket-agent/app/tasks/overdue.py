"""超时标记：每 5 分钟扫描 due_at 已过且未标记的工单。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import OVERDUE_SCAN_STATUSES
from app.core.db import SessionLocal
from app.models.work_order import WorkOrder, WorkOrderRecord
from app.services.alert_service import create_work_order_alert
from app.services.log_service import write_log_safely
from app.tasks.celery_app import celery_app
from app.tasks.common import log_task, retry_delay


def _mark_overdue(db: Session) -> int:
    now = datetime.now(UTC)
    orders = db.scalars(
        select(WorkOrder).where(
            WorkOrder.status.in_(OVERDUE_SCAN_STATUSES),
            WorkOrder.due_at.is_not(None),
            WorkOrder.due_at < now,
            WorkOrder.is_overdue.is_(False),
            WorkOrder.deleted_at.is_(None),
        )
    ).all()
    for order in orders:
        order.is_overdue = True
        order.overdue_at = now
        db.add(
            WorkOrderRecord(
                work_order_id=order.id,
                action="timeout_auto",
                from_status=order.status,
                to_status=order.status,
                operator_name="系统",
                content="系统标记超时",
            )
        )
        # 预警与超时标记同事务，回滚时一起回滚
        create_work_order_alert(
            db,
            order_id=order.id,
            category=order.category,
            department_id=order.department_id,
            assignee_id=order.assignee_id,
        )
    log_task(
        db,
        action="mark_overdue_orders",
        detail={"marked": len(orders)},
    )
    db.commit()
    return len(orders)


@celery_app.task(bind=True, name="mark_overdue_orders", max_retries=3)
def mark_overdue_orders(self) -> dict[str, int]:
    try:
        with SessionLocal() as db:
            return {"marked": _mark_overdue(db)}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            write_log_safely(
                db,
                log_type="system",
                resource="task",
                action="mark_overdue_orders",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
        raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc
