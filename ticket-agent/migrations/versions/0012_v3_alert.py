"""V3 预警：alerts、safe_stock_configs

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("alert_no", sa.String(16), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger()),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("metric_value", sa.Numeric(18, 4)),
        sa.Column("threshold_value", sa.Numeric(18, 4)),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.BigInteger()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.BigInteger()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("handle_note", sa.String(500)),
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
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name="fk_alerts_department"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], name="fk_alerts_ack_user"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], name="fk_alerts_close_user"),
        sa.UniqueConstraint("alert_no", name="uq_alerts_no"),
        sa.CheckConstraint(
            "alert_type IN ('low_stock','overstock','purchase_price_up','sales_price_down',"
            "'receivable_overdue','payable_due','work_order_overdue','device_fault_repeat',"
            "'profit_decline')",
            name="ck_alerts_type",
        ),
        sa.CheckConstraint("level IN ('critical','warning','info')", name="ck_alerts_level"),
        sa.CheckConstraint("status IN ('open','acknowledged','closed')", name="ck_alerts_status"),
        sa.CheckConstraint(
            "acknowledged_at IS NULL OR acknowledged_by IS NOT NULL",
            name="ck_alerts_ack",
        ),
        sa.CheckConstraint(
            "closed_at IS NULL OR (closed_by IS NOT NULL AND handle_note IS NOT NULL)",
            name="ck_alerts_close",
        ),
        sa.CheckConstraint(
            "status <> 'closed' OR handle_note IS NOT NULL", name="ck_alerts_closed_note"
        ),
    )
    op.create_index("idx_alerts_dedupe", "alerts", ["dedupe_key", "triggered_at"])
    op.create_index("idx_alerts_status", "alerts", ["status", "triggered_at"])
    op.create_index("idx_alerts_department", "alerts", ["department_id", "triggered_at"])

    op.create_table(
        "safe_stock_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("safe_quantity", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.BigInteger()),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_safe_stock_product"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], name="fk_safe_stock_warehouse"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_safe_stock_user"),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_safe_stock_product_warehouse"),
        sa.CheckConstraint("safe_quantity >= 0", name="ck_safe_stock_quantity"),
    )


def downgrade() -> None:
    op.drop_table("safe_stock_configs")
    op.drop_index("idx_alerts_department", table_name="alerts")
    op.drop_index("idx_alerts_status", table_name="alerts")
    op.drop_index("idx_alerts_dedupe", table_name="alerts")
    op.drop_table("alerts")
