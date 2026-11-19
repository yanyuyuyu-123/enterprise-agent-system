"""单据序号类型增加用车申请 CA

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEQ_TYPES_WITH_CA = "'WO','PO','SO','AC','SM','SC','FR','CF','CA'"
SEQ_TYPES_WITHOUT_CA = "'WO','PO','SO','AC','SM','SC','FR','CF'"


def upgrade() -> None:
    op.drop_constraint("ck_seq_type", "order_no_sequences", type_="check")
    op.create_check_constraint(
        "ck_seq_type", "order_no_sequences", f"seq_type IN ({SEQ_TYPES_WITH_CA})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM order_no_sequences WHERE seq_type = 'CA'")
    op.drop_constraint("ck_seq_type", "order_no_sequences", type_="check")
    op.create_check_constraint(
        "ck_seq_type", "order_no_sequences", f"seq_type IN ({SEQ_TYPES_WITHOUT_CA})"
    )
