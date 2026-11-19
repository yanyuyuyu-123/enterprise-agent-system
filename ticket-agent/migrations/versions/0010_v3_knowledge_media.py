"""V3 知识库收尾：图片/音视频字段、转写表与时间戳分块

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("media_type", sa.String(16), nullable=False, server_default="document"),
    )
    op.add_column("knowledge_documents", sa.Column("duration_ms", sa.Integer()))
    op.add_column("knowledge_documents", sa.Column("ocr_engine", sa.String(32)))

    op.drop_constraint("ck_kd_file_ext", "knowledge_documents", type_="check")
    op.create_check_constraint(
        "ck_kd_file_ext",
        "knowledge_documents",
        "file_ext IN ('pdf','docx','xlsx','csv','md','txt','png','jpg','jpeg','mp3','wav','mp4')",
    )

    op.add_column("knowledge_chunks", sa.Column("start_ms", sa.Integer()))
    op.add_column("knowledge_chunks", sa.Column("end_ms", sa.Integer()))

    op.create_table(
        "knowledge_transcripts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="zh"),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column(
            "segments",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("error_message", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_transcripts_document",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('success','failed')", name="ck_knowledge_transcripts_status"
        ),
    )
    op.create_index(
        "idx_knowledge_transcripts_document",
        "knowledge_transcripts",
        ["document_id", "document_version"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_transcripts_document", table_name="knowledge_transcripts")
    op.drop_table("knowledge_transcripts")
    op.drop_column("knowledge_chunks", "end_ms")
    op.drop_column("knowledge_chunks", "start_ms")
    op.drop_constraint("ck_kd_file_ext", "knowledge_documents", type_="check")
    op.create_check_constraint(
        "ck_kd_file_ext",
        "knowledge_documents",
        "file_ext IN ('pdf','docx','xlsx','csv','md','txt')",
    )
    op.drop_column("knowledge_documents", "ocr_engine")
    op.drop_column("knowledge_documents", "duration_ms")
    op.drop_column("knowledge_documents", "media_type")
