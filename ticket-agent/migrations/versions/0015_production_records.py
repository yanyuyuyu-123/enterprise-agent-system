"""煤炭业务：production_records（每日生产记录）

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "production_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("record_no", sa.String(24), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("team", sa.String(32), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("wash_yield", sa.Numeric(5, 2), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_mock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("remark", sa.String(255), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_production_product"),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_production_department"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_production_creator"),
        sa.UniqueConstraint("record_no", name="uq_production_record_no"),
    )
    op.create_index("ix_production_records_date", "production_records", ["record_date"])
    op.create_index(
        "ix_production_records_product", "production_records", ["product_id", "record_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_production_records_product", table_name="production_records")
    op.drop_index("ix_production_records_date", table_name="production_records")
    op.drop_table("production_records")
