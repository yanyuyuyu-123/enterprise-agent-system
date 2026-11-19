"""会计/财务负责人补客户与供应商只读权限（财务记录选择往来单位）

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSITIONS = ("accountant", "finance_head")
RESOURCES = ("customer", "supplier")


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
