"""制单员/理货员补订单只读权限（出入库单需选择来源单据）

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSITIONS = ("document_clerk", "tally_clerk")
RESOURCES = ("sales_order", "purchase_order")


def upgrade() -> None:
    for code in POSITIONS:
        for resource in RESOURCES:
            op.execute(
                f"""
                INSERT INTO position_permissions (position_id, resource, action, data_scope)
                SELECT p.id, '{resource}', 'read', 'company'
                FROM positions p
                WHERE p.code = '{code}'
                  AND p.deleted_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM position_permissions pp
                    WHERE pp.position_id = p.id
                      AND pp.resource = '{resource}'
                      AND pp.action = 'read'
                  )
                """
            )


def downgrade() -> None:
    for code in POSITIONS:
        for resource in RESOURCES:
            op.execute(
                f"""
                DELETE FROM position_permissions
                WHERE resource = '{resource}' AND action = 'read'
                  AND position_id IN (SELECT id FROM positions WHERE code = '{code}')
                """
            )
