"""业务一致性：订单履约状态、出入库红冲、退货类型

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FULFILLMENT = "('none','partial','completed')"
MOVEMENT_TYPES = "('inbound','outbound','purchase_return','sales_return','stocktake_in','stocktake_out','loss')"
FINANCE_TYPES = "('income','cost','expense','receivable','payable','cost_reversal','income_reversal')"


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column(
        "sales_orders",
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column("stock_movements", sa.Column("reversal_of_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "stock_movements", sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_stock_movements_reversal",
        "stock_movements",
        "stock_movements",
        ["reversal_of_id"],
        ["id"],
    )
    op.create_index(
        "uq_stock_movements_reversal_of",
        "stock_movements",
        ["reversal_of_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_id IS NOT NULL"),
    )

    # 回填历史履约状态（超量按 completed 处理）
    op.execute(
        """
        UPDATE purchase_orders po
        SET fulfillment_status = CASE
            WHEN COALESCE(executed.qty, 0) <= 0 THEN 'none'
            WHEN executed.qty >= ordered.qty THEN 'completed'
            ELSE 'partial'
        END
        FROM (
            SELECT po2.id,
                   COALESCE((SELECT SUM(i.quantity) FROM purchase_order_items i
                             WHERE i.purchase_order_id = po2.id), 0) AS qty
            FROM purchase_orders po2
        ) ordered
        LEFT JOIN (
            SELECT sm.source_id, SUM(smi.quantity) AS qty
            FROM stock_movements sm
            JOIN stock_movement_items smi ON smi.movement_id = sm.id
            WHERE sm.source_type = 'purchase_order'
              AND sm.status = 'approved'
              AND sm.movement_type = 'inbound'
              AND sm.reversed_at IS NULL
            GROUP BY sm.source_id
        ) executed ON executed.source_id = ordered.id
        WHERE po.id = ordered.id
        """
    )
    op.execute(
        """
        UPDATE sales_orders so
        SET fulfillment_status = CASE
            WHEN COALESCE(executed.qty, 0) <= 0 THEN 'none'
            WHEN executed.qty >= ordered.qty THEN 'completed'
            ELSE 'partial'
        END
        FROM (
            SELECT so2.id,
                   COALESCE((SELECT SUM(i.quantity) FROM sales_order_items i
                             WHERE i.sales_order_id = so2.id), 0) AS qty
            FROM sales_orders so2
        ) ordered
        LEFT JOIN (
            SELECT sm.source_id, SUM(smi.quantity) AS qty
            FROM stock_movements sm
            JOIN stock_movement_items smi ON smi.movement_id = sm.id
            WHERE sm.source_type = 'sales_order'
              AND sm.status = 'approved'
              AND sm.movement_type = 'outbound'
              AND sm.reversed_at IS NULL
            GROUP BY sm.source_id
        ) executed ON executed.source_id = ordered.id
        WHERE so.id = ordered.id
        """
    )

    op.create_check_constraint(
        "ck_po_fulfillment", "purchase_orders", f"fulfillment_status IN {FULFILLMENT}"
    )
    op.create_check_constraint(
        "ck_so_fulfillment", "sales_orders", f"fulfillment_status IN {FULFILLMENT}"
    )
    op.drop_constraint("ck_sm_type", "stock_movements", type_="check")
    op.create_check_constraint(
        "ck_sm_type", "stock_movements", f"movement_type IN {MOVEMENT_TYPES}"
    )
    op.drop_constraint("ck_fin_type", "finance_records", type_="check")
    op.create_check_constraint("ck_fin_type", "finance_records", f"record_type IN {FINANCE_TYPES}")


def downgrade() -> None:
    op.drop_constraint("ck_fin_type", "finance_records", type_="check")
    op.create_check_constraint(
        "ck_fin_type",
        "finance_records",
        "record_type IN ('income','cost','expense','receivable','payable')",
    )
    op.execute(
        "DELETE FROM finance_records WHERE record_type IN ('cost_reversal','income_reversal')"
    )
    op.drop_constraint("ck_sm_type", "stock_movements", type_="check")
    op.create_check_constraint(
        "ck_sm_type",
        "stock_movements",
        "movement_type IN ('inbound','outbound','stocktake_in','stocktake_out','loss')",
    )
    op.drop_constraint("ck_po_fulfillment", "purchase_orders", type_="check")
    op.drop_constraint("ck_so_fulfillment", "sales_orders", type_="check")
    op.drop_index("uq_stock_movements_reversal_of", table_name="stock_movements")
    op.drop_constraint("fk_stock_movements_reversal", "stock_movements", type_="foreignkey")
    op.drop_column("stock_movements", "reversed_at")
    op.drop_column("stock_movements", "reversal_of_id")
    op.drop_column("sales_orders", "fulfillment_status")
    op.drop_column("purchase_orders", "fulfillment_status")
