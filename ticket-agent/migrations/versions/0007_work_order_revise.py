"""工单驳回后由创建人修改并重新提交

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "('supplementing','pending_assignment','pending_process','processing','pending_review',"
    "'rejected','completed','cancelled')"
)
ACTIONS = (
    "('create','supplement','assign','reassign','start','submit_result','revise',"
    "'review_approve','review_reject','recall','transfer_request','transfer_approve',"
    "'transfer_reject','timeout_auto')"
)


def upgrade() -> None:
    op.drop_constraint("ck_wo_status", "work_orders", type_="check")
    op.create_check_constraint("ck_wo_status", "work_orders", f"status IN {STATUSES}")

    op.drop_constraint("ck_wo_record_action", "work_order_records", type_="check")
    op.create_check_constraint(
        "ck_wo_record_action", "work_order_records", f"action IN {ACTIONS}"
    )


def downgrade() -> None:
    op.execute("UPDATE work_orders SET status='processing' WHERE status='rejected'")
    op.execute("DELETE FROM work_order_records WHERE action='revise'")
    op.drop_constraint("ck_wo_record_action", "work_order_records", type_="check")
    op.create_check_constraint(
        "ck_wo_record_action",
        "work_order_records",
        "action IN ('create','supplement','assign','reassign','start','submit_result',"
        "'review_approve','review_reject','recall','transfer_request','transfer_approve',"
        "'transfer_reject','timeout_auto')",
    )
    op.drop_constraint("ck_wo_status", "work_orders", type_="check")
    op.create_check_constraint(
        "ck_wo_status",
        "work_orders",
        "status IN ('supplementing','pending_assignment','pending_process','processing',"
        "'pending_review','completed','cancelled')",
    )
