"""出入库单新建/执行权限：总经理、业务负责人、业务经理

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = (
    ("general_manager", "company"),
    ("biz_head", "company"),
    ("biz_manager", "department"),
)


def upgrade() -> None:
    for code, scope in GRANTS:
        op.execute(
            f"""
            INSERT INTO position_permissions (position_id, resource, action, data_scope)
            SELECT p.id, 'inventory', v.action, '{scope}'
            FROM positions p
            CROSS JOIN (VALUES ('create'), ('update')) AS v(action)
            WHERE p.code = '{code}'
              AND p.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM position_permissions pp
                WHERE pp.position_id = p.id
                  AND pp.resource = 'inventory'
                  AND pp.action = v.action
                  AND pp.data_scope = '{scope}'
              )
            """
        )


def downgrade() -> None:
    for code, scope in GRANTS:
        op.execute(
            f"""
            DELETE FROM position_permissions
            WHERE resource = 'inventory'
              AND action IN ('create', 'update')
              AND data_scope = '{scope}'
              AND position_id IN (
                SELECT id FROM positions WHERE code = '{code}'
              )
            """
        )
