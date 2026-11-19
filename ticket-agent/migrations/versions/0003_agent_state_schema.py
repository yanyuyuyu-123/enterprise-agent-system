"""Agent 会话状态使用独立 schema，checkpointer 表由 LangGraph 启动时创建

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS agent_state")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS agent_state CASCADE")
