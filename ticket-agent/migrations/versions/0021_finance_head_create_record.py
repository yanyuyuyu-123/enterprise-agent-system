"""财务负责人可录入财务记录（收入/支出）

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'finance_record', 'create', 'company'
        FROM positions p
        WHERE p.code = 'finance_head'
          AND p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = 'finance_record'
              AND pp.action = 'create'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM position_permissions
        WHERE resource = 'finance_record' AND action = 'create'
          AND position_id IN (SELECT id FROM positions WHERE code = 'finance_head')
        """
    )
