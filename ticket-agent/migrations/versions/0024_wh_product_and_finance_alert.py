"""仓库负责人补产品只读；财务负责人预警处理范围放宽到全公司

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 安全库存配置需要选择产品
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'product', 'read', 'company'
        FROM positions p
        WHERE p.code = 'warehouse_head'
          AND p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = 'product'
              AND pp.action = 'read'
          )
        """
    )
    # 毛利率下降等公司级预警的接收人包含财务负责人，处理范围需覆盖全公司
    op.execute(
        """
        UPDATE position_permissions
        SET data_scope = 'company'
        WHERE resource = 'alert' AND action = 'update'
          AND position_id IN (SELECT id FROM positions WHERE code = 'finance_head')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM position_permissions
        WHERE resource = 'product' AND action = 'read'
          AND position_id IN (SELECT id FROM positions WHERE code = 'warehouse_head')
        """
    )
    op.execute(
        """
        UPDATE position_permissions
        SET data_scope = 'department'
        WHERE resource = 'alert' AND action = 'update'
          AND position_id IN (SELECT id FROM positions WHERE code = 'finance_head')
        """
    )
