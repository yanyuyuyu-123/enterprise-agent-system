"""制单员/理货员补产品只读权限（建单时需要选商品）

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSITIONS = ("document_clerk", "tally_clerk")


def upgrade() -> None:
    for code in POSITIONS:
        op.execute(
            f"""
            INSERT INTO position_permissions (position_id, resource, action, data_scope)
            SELECT p.id, 'product', 'read', 'company'
            FROM positions p
            WHERE p.code = '{code}'
              AND p.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM position_permissions pp
                WHERE pp.position_id = p.id
                  AND pp.resource = 'product'
                  AND pp.action = 'read'
              )
            """
        )


def downgrade() -> None:
    for code in POSITIONS:
        op.execute(
            f"""
            DELETE FROM position_permissions
            WHERE resource = 'product' AND action = 'read'
              AND position_id IN (SELECT id FROM positions WHERE code = '{code}')
            """
        )
