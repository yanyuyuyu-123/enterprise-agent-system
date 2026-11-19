"""知识库上传/删除权限收紧：仅系统管理员（人事负责人）与总经理

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 移除除系统管理员（人事负责人）与总经理外所有岗位的知识库上传/删除授权
    op.execute(
        """
        DELETE FROM position_permissions
        WHERE resource = 'knowledge_document'
          AND action IN ('create', 'delete')
        """
    )

    # 系统管理员（人事负责人）与总经理：全公司范围上传/删除
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'knowledge_document', v.action, 'company'
        FROM positions p
        CROSS JOIN (VALUES ('create'), ('delete')) AS v(action)
        WHERE p.code IN ('hr_head', 'general_manager')
          AND p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = 'knowledge_document'
              AND pp.action = v.action
              AND pp.data_scope = 'company'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM position_permissions
        WHERE resource = 'knowledge_document'
          AND action IN ('create', 'delete')
          AND position_id IN (
            SELECT id FROM positions
            WHERE code IN ('hr_head', 'general_manager')
          )
        """
    )
    # 恢复 V2 种子中的原授权
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'knowledge_document', v.action, v.data_scope
        FROM positions p
        JOIN (VALUES
          ('hr_head','create','company'),
          ('hr_head','delete','company'),
          ('hr_specialist','create','company'),
          ('hr_specialist','delete','company'),
          ('finance_head','create','department'),
          ('finance_head','delete','department'),
          ('biz_head','create','department'),
          ('biz_head','delete','department'),
          ('production_head','create','department'),
          ('production_head','delete','department'),
          ('security_head','create','department'),
          ('security_head','delete','department'),
          ('logistics_head','create','department'),
          ('logistics_head','delete','department')
        ) AS v(code, action, data_scope) ON p.code = v.code
        WHERE p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = 'knowledge_document'
              AND pp.action = v.action
              AND pp.data_scope = v.data_scope
          )
        """
    )
