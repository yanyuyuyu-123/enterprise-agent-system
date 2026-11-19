"""出入库单/盘点单所属部门允许为空：总经理等无部门账号也能建单

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("stock_movements", "stock_checks"):
        op.alter_column(
            table,
            "department_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )


def downgrade() -> None:
    for table in ("stock_movements", "stock_checks"):
        op.alter_column(
            table,
            "department_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
