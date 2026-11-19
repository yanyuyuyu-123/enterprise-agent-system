"""扩展站内通知类型：出入库单、盘点单

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPE_CONSTRAINT = (
    "type IN ('work_order_assigned','work_order_review','work_order_rejected',"
    "'work_order_completed','work_order_recalled','transfer_request','transfer_result',"
    "'account_changed','work_order_overdue','report_published','alert_triggered','system',"
    "'stock_movement','stock_check')"
)
RELATED_TYPE_CONSTRAINT = (
    "related_type IS NULL OR related_type IN "
    "('work_order','report','alert','account','system','stock_movement','stock_check')"
)


def upgrade() -> None:
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.drop_constraint("ck_notifications_related_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications", TYPE_CONSTRAINT)
    op.create_check_constraint(
        "ck_notifications_related_type", "notifications", RELATED_TYPE_CONSTRAINT
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM notifications WHERE type IN ('stock_movement','stock_check') "
        "OR related_type IN ('stock_movement','stock_check')"
    )
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.drop_constraint("ck_notifications_related_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ('work_order_assigned','work_order_review','work_order_rejected',"
        "'work_order_completed','work_order_recalled','transfer_request','transfer_result',"
        "'account_changed','work_order_overdue','report_published','alert_triggered','system')",
    )
    op.create_check_constraint(
        "ck_notifications_related_type",
        "notifications",
        "related_type IS NULL OR related_type IN "
        "('work_order','report','alert','account','system')",
    )
