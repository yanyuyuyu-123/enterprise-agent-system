"""知识文档所属部门允许为空：总经理上传的全公司文档不归属具体部门

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "knowledge_documents",
        "department_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_documents",
        "department_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
