"""users 增加直接上级字段，供 self_and_subordinates 数据范围使用

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("manager_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_users_manager", "users", "users", ["manager_id"], ["id"])
    op.create_index("idx_users_manager_id", "users", ["manager_id"])


def downgrade() -> None:
    op.drop_index("idx_users_manager_id", table_name="users")
    op.drop_constraint("fk_users_manager", "users", type_="foreignkey")
    op.drop_column("users", "manager_id")
