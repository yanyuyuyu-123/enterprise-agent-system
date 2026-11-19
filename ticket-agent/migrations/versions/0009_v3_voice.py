"""V3 语音：voice_files、voice_transcripts，并扩展 system_configs 分类

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_files",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_ext", sa.String(8), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_voice_files_user"),
        sa.CheckConstraint("file_ext IN ('wav','mp3')", name="ck_voice_files_ext"),
        sa.CheckConstraint("purpose IN ('asr_input','tts_output')", name="ck_voice_files_purpose"),
    )
    op.create_index("idx_voice_files_user", "voice_files", ["user_id", "created_at"])
    op.create_index("idx_voice_files_expires", "voice_files", ["expires_at"])

    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("voice_file_id", sa.BigInteger(), nullable=False),
        sa.Column("asr_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text()),
        sa.Column("rewritten_text", sa.Text()),
        sa.Column("final_text", sa.Text()),
        sa.Column("intent", sa.String(32)),
        sa.Column(
            "entities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("asr_confidence", sa.Numeric(5, 4)),
        sa.Column("semantic_confidence", sa.Numeric(5, 4)),
        sa.Column(
            "suspected_errors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "needs_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("confirmation_question", sa.String(500)),
        sa.Column(
            "confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_voice_transcripts_user"),
        sa.ForeignKeyConstraint(
            ["voice_file_id"],
            ["voice_files.id"],
            name="fk_voice_transcripts_file",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("voice_file_id", name="uq_voice_transcripts_file"),
        sa.CheckConstraint(
            "asr_confidence IS NULL OR asr_confidence BETWEEN 0 AND 1",
            name="ck_voice_transcripts_asr_conf",
        ),
        sa.CheckConstraint(
            "semantic_confidence IS NULL OR semantic_confidence BETWEEN 0 AND 1",
            name="ck_voice_transcripts_semantic_conf",
        ),
        sa.CheckConstraint(
            "confirmed = false OR confirmed_at IS NOT NULL",
            name="ck_voice_transcripts_confirmed",
        ),
    )
    op.create_index("idx_voice_transcripts_user", "voice_transcripts", ["user_id", "created_at"])

    op.drop_constraint("ck_configs_category", "system_configs", type_="check")
    op.create_check_constraint(
        "ck_configs_category",
        "system_configs",
        "category IN ('work_order','inventory','finance','report','agent','security','auth',"
        "'log','knowledge','voice','alert')",
    )

    # 语音与安全库存是 V3 新增资源，需同步放开权限表的资源白名单
    op.drop_constraint("ck_position_permissions_resource", "position_permissions", type_="check")
    op.create_check_constraint(
        "ck_position_permissions_resource",
        "position_permissions",
        "resource IN ('work_order','work_order_assign','work_order_review','work_order_transfer',"
        "'report','knowledge_document','operation_log','system_log','account','org','device',"
        "'purchase_order','sales_order','customer','supplier','product','inventory',"
        "'finance_record','config','alert','voice','safe_stock')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_configs_category", "system_configs", type_="check")
    op.create_check_constraint(
        "ck_configs_category",
        "system_configs",
        "category IN ('work_order','inventory','finance','report','agent','security','auth',"
        "'log','knowledge')",
    )
    op.drop_index("idx_voice_transcripts_user", table_name="voice_transcripts")
    op.drop_table("voice_transcripts")
    op.drop_index("idx_voice_files_expires", table_name="voice_files")
    op.drop_index("idx_voice_files_user", table_name="voice_files")
    op.drop_table("voice_files")

    op.drop_constraint("ck_position_permissions_resource", "position_permissions", type_="check")
    op.create_check_constraint(
        "ck_position_permissions_resource",
        "position_permissions",
        "resource IN ('work_order','work_order_assign','work_order_review','work_order_transfer',"
        "'report','knowledge_document','operation_log','system_log','account','org','device',"
        "'purchase_order','sales_order','customer','supplier','product','inventory',"
        "'finance_record','config','alert')",
    )
