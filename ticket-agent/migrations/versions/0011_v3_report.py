"""V3 报告：reports、report_viewers

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("report_no", sa.String(16), nullable=False),
        sa.Column("report_type", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("compare_start", sa.Date()),
        sa.Column("compare_end", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="generating"),
        sa.Column("file_path", sa.String(512)),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("report_no", name="uq_reports_no"),
        sa.UniqueConstraint("report_type", "period_start", "period_end", name="uq_reports_period"),
        sa.CheckConstraint(
            "report_type IN ('daily','weekly','monthly','yearly')", name="ck_reports_type"
        ),
        sa.CheckConstraint(
            "status IN ('generating','generated','failed')", name="ck_reports_status"
        ),
        sa.CheckConstraint("period_start <= period_end", name="ck_reports_period"),
    )
    op.create_index("idx_reports_type_period", "reports", ["report_type", "period_end"])

    op.create_table(
        "report_viewers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_report_viewers_user"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], name="fk_report_viewers_granted_by"),
        sa.UniqueConstraint("user_id", name="uq_report_viewers_user"),
    )


def downgrade() -> None:
    op.drop_table("report_viewers")
    op.drop_index("idx_reports_type_period", table_name="reports")
    op.drop_table("reports")
