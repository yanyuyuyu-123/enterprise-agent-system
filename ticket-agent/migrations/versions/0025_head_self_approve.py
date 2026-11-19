"""负责人自建单据免审：补业务负责人、仓库负责人建单权限

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = (
    ("biz_head", "sales_order", "create"),
    ("biz_head", "purchase_order", "create"),
    ("warehouse_head", "inventory", "create"),
)


def upgrade() -> None:
    for position, resource, action in GRANTS:
        op.execute(
            f"""
            INSERT INTO position_permissions (position_id, resource, action, data_scope)
            SELECT p.id, '{resource}', '{action}', 'company'
            FROM positions p
            WHERE p.code = '{position}'
              AND p.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM position_permissions pp
                WHERE pp.position_id = p.id
                  AND pp.resource = '{resource}'
                  AND pp.action = '{action}'
              )
            """
        )


def downgrade() -> None:
    for position, resource, action in GRANTS:
        op.execute(
            f"""
            DELETE FROM position_permissions
            WHERE resource = '{resource}' AND action = '{action}'
              AND position_id IN (SELECT id FROM positions WHERE code = '{position}')
            """
        )
