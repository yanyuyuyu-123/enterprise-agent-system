"""V2 知识库表与 pgvector 扩展

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024


def _audit() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("doc_no", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="other"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_ext", sa.String(16), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("visibility_scope", sa.String(24), nullable=False, server_default="department"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding_model", sa.String(64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_knowledge_documents_department"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_knowledge_documents_owner"),
        sa.CheckConstraint(
            "category IN ('contract','policy','manual','quotation','process','other')",
            name="ck_kd_category",
        ),
        sa.CheckConstraint(
            "file_ext IN ('pdf','docx','xlsx','csv','md','txt')", name="ck_kd_file_ext"
        ),
        sa.CheckConstraint("visibility_scope IN ('company','department')", name="ck_kd_scope"),
        sa.CheckConstraint(
            "status IN ('pending','parsing','ready','need_ocr','failed','disabled')",
            name="ck_kd_status",
        ),
        sa.CheckConstraint("file_size >= 0", name="ck_kd_file_size"),
        sa.CheckConstraint("chunk_count >= 0", name="ck_kd_chunk_count"),
        sa.CheckConstraint("version >= 1", name="ck_kd_version"),
    )
    op.create_index(
        "uq_knowledge_documents_doc_no",
        "knowledge_documents",
        ["doc_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_kd_status_department", "knowledge_documents", ["status", "department_id"])
    op.create_index(
        "idx_kd_scope_department", "knowledge_documents", ["visibility_scope", "department_id"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(255), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(64), nullable=True),
        sa.Column("row_no", sa.Integer(), nullable=True),
        sa.Column("paragraph_no", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_chunks_document",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "document_version",
            "chunk_index",
            name="uq_chunks_document_version_index",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_kc_index"),
        sa.CheckConstraint("document_version >= 1", name="ck_kc_version"),
    )
    op.create_index(
        "idx_chunks_embedding",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_embedding", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("idx_kd_scope_department", table_name="knowledge_documents")
    op.drop_index("idx_kd_status_department", table_name="knowledge_documents")
    op.drop_index("uq_knowledge_documents_doc_no", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    # 扩展可能被其他库对象使用，降级不删除 vector 扩展
