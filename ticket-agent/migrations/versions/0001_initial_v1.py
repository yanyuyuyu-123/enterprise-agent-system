"""V1 初始表结构与初始数据

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPES = "('company','department','self_and_subordinates','self','business_domain')"
DOMAINS = "('inventory','finance','hr','sales','purchase','production','security','logistics')"
ACTIONS = (
    "('create','read','update','delete','assign','review','transfer','approve','export','config')"
)
RESOURCES = (
    "('work_order','work_order_assign','work_order_review','work_order_transfer','report',"
    "'knowledge_document','operation_log','system_log','account','org','device','purchase_order',"
    "'sales_order','customer','supplier','product','inventory','finance_record','config','alert')"
)
STATUSES = (
    "('supplementing','pending_assignment','pending_process','processing','pending_review',"
    "'completed','cancelled')"
)


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


def _created() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def upgrade() -> None:
    # ---------- 组织与账号 ----------
    op.create_table(
        "departments",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(255), nullable=True),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["departments.id"], name="fk_departments_parent"),
    )
    op.create_index(
        "uq_departments_code",
        "departments",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_departments_parent_id", "departments", ["parent_id"])

    op.create_table(
        "positions",
        _id(),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("data_scope", sa.String(24), nullable=False),
        sa.Column("business_domain", sa.String(24), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_positions_department"
        ),
        sa.CheckConstraint(f"data_scope IN {SCOPES}", name="ck_positions_data_scope"),
        sa.CheckConstraint(
            f"business_domain IS NULL OR business_domain IN {DOMAINS}",
            name="ck_positions_business_domain",
        ),
        sa.CheckConstraint(
            "(data_scope = 'business_domain') = (business_domain IS NOT NULL)",
            name="ck_positions_domain",
        ),
    )
    op.create_index(
        "uq_positions_code",
        "positions",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_positions_department_id", "positions", ["department_id"])

    op.create_table(
        "users",
        _id(),
        sa.Column("employee_no", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(128), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("hired_at", sa.Date(), nullable=True),
        sa.Column("left_at", sa.Date(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name="fk_users_department"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_users_status"),
    )
    op.create_index(
        "uq_users_employee_no",
        "users",
        ["employee_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_users_department_id", "users", ["department_id"])
    op.create_index("idx_users_status", "users", ["status"])

    op.create_table(
        "user_positions",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_positions_user", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name="fk_user_positions_position",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_user_positions",
        "user_positions",
        ["user_id", "position_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "position_permissions",
        _id(),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("resource", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("data_scope", sa.String(24), nullable=False),
        sa.Column("business_domain", sa.String(24), nullable=True),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name="fk_position_permissions_position",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "position_id",
            "resource",
            "action",
            "data_scope",
            name="uq_position_permissions",
        ),
        sa.CheckConstraint(f"resource IN {RESOURCES}", name="ck_position_permissions_resource"),
        sa.CheckConstraint(f"action IN {ACTIONS}", name="ck_position_permissions_action"),
        sa.CheckConstraint(f"data_scope IN {SCOPES}", name="ck_position_permissions_scope"),
        sa.CheckConstraint(
            f"business_domain IS NULL OR business_domain IN {DOMAINS}",
            name="ck_position_permissions_business_domain",
        ),
        sa.CheckConstraint(
            "(data_scope = 'business_domain') = (business_domain IS NOT NULL)",
            name="ck_position_permissions_domain",
        ),
    )

    op.create_table(
        "devices",
        _id(),
        sa.Column("device_no", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(128), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.String(255), nullable=True),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_devices_department"
        ),
        sa.CheckConstraint(
            "status IN ('running','idle','repairing','scrapped')", name="ck_devices_status"
        ),
    )
    op.create_index(
        "uq_devices_device_no",
        "devices",
        ["device_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_devices_department_id", "devices", ["department_id"])
    op.create_index("idx_devices_status", "devices", ["status"])

    # ---------- 工单主表与明细 ----------
    op.create_table(
        "work_order_categories",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_audit(),
        sa.UniqueConstraint("code", name="uq_work_order_categories_code"),
    )

    op.create_table(
        "work_orders",
        _id(),
        sa.Column("order_no", sa.String(20), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(32), nullable=False, server_default="supplementing"),
        sa.Column("source_type", sa.String(16), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("creator_id", sa.BigInteger(), nullable=False),
        sa.Column("assignee_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_overdue", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("overdue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recall_reason", sa.String(500), nullable=True),
        sa.Column("transfer_to_id", sa.BigInteger(), nullable=True),
        sa.Column("transfer_status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_audit(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["category"],
            ["work_order_categories.code"],
            name="fk_wo_category",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name="fk_wo_department"),
        sa.ForeignKeyConstraint(
            ["creator_id"], ["users.id"], name="fk_wo_creator", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], name="fk_wo_assignee"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_wo_reviewer"),
        sa.ForeignKeyConstraint(["transfer_to_id"], ["users.id"], name="fk_wo_transfer_to"),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_wo_status"),
        sa.CheckConstraint("priority IN ('low','normal','high','urgent')", name="ck_wo_priority"),
        sa.CheckConstraint(
            "transfer_status IN ('none','pending','approved','rejected')",
            name="ck_wo_transfer_status",
        ),
        sa.CheckConstraint(
            "source_type IS NULL OR source_type IN ('device','product','customer','order')",
            name="ck_wo_source_type",
        ),
        sa.CheckConstraint(
            "status = 'supplementing' OR category <> 'device_repair' OR source_type = 'device'",
            name="ck_wo_device",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL", name="ck_wo_completed"
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND recall_reason IS NOT NULL)",
            name="ck_wo_cancelled",
        ),
        sa.CheckConstraint("is_overdue = false OR overdue_at IS NOT NULL", name="ck_wo_overdue"),
        sa.CheckConstraint("version >= 1", name="ck_wo_version"),
    )
    op.create_index("uq_work_orders_order_no", "work_orders", ["order_no"], unique=True)
    op.create_index("idx_wo_department_status", "work_orders", ["department_id", "status"])
    op.create_index("idx_wo_assignee_status", "work_orders", ["assignee_id", "status"])
    op.create_index(
        "idx_wo_creator_created",
        "work_orders",
        ["creator_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_wo_due_overdue",
        "work_orders",
        ["due_at"],
        postgresql_where=sa.text("is_overdue = false"),
    )
    op.create_index("idx_wo_status_created", "work_orders", ["status", sa.text("created_at DESC")])
    op.create_index("idx_wo_reviewer_status", "work_orders", ["reviewer_id", "status"])
    op.create_index("idx_wo_category_status", "work_orders", ["category", "status"])

    op.create_table(
        "work_order_device",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("device_no_snapshot", sa.String(64), nullable=True),
        sa.Column("device_name_snapshot", sa.String(128), nullable=True),
        sa.Column("fault_description", sa.Text(), nullable=True),
        sa.Column("repair_result", sa.Text(), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], name="fk_wo_device_order", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_wo_device_device", ondelete="RESTRICT"
        ),
    )
    op.create_index("uq_wo_device_order", "work_order_device", ["work_order_id"], unique=True)
    op.create_index("idx_wo_device_device", "work_order_device", ["device_id"])

    op.create_table(
        "work_order_expense",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("expense_type", sa.String(32), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_wo_expense_order",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name="ck_wo_expense_amount"),
        sa.CheckConstraint(
            "expense_type IS NULL OR expense_type IN "
            "('travel','transport','office','entertainment','purchase','other')",
            name="ck_wo_expense_type",
        ),
    )
    op.create_index("uq_wo_expense_order", "work_order_expense", ["work_order_id"], unique=True)

    op.create_table(
        "work_order_patrol",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("patrol_area", sa.String(128), nullable=True),
        sa.Column("hazard_description", sa.Text(), nullable=True),
        sa.Column("rectification_result", sa.Text(), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], name="fk_wo_patrol_order", ondelete="RESTRICT"
        ),
    )
    op.create_index("uq_wo_patrol_order", "work_order_patrol", ["work_order_id"], unique=True)

    op.create_table(
        "work_order_transport",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("trip_no", sa.String(64), nullable=True),
        sa.Column("exception_type", sa.String(32), nullable=True),
        sa.Column("handling_result", sa.Text(), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_wo_transport_order",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("uq_wo_transport_order", "work_order_transport", ["work_order_id"], unique=True)
    op.create_index("idx_wo_transport_trip", "work_order_transport", ["trip_no"])

    op.create_table(
        "work_order_records",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("operator_name", sa.String(64), nullable=False),
        sa.Column("operator_position", sa.String(48), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("is_agent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("agent_session_id", sa.String(64), nullable=True),
        sa.Column(
            "detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        _created(),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_wo_record_order",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action IN ('create','supplement','assign','reassign','start','submit_result',"
            "'review_approve','review_reject','recall','transfer_request','transfer_approve',"
            "'transfer_reject','timeout_auto')",
            name="ck_wo_record_action",
        ),
    )
    op.create_index(
        "idx_wo_record_order_created", "work_order_records", ["work_order_id", "created_at"]
    )
    op.create_index(
        "idx_wo_record_action", "work_order_records", ["action", sa.text("created_at DESC")]
    )

    op.create_table(
        "work_order_approvals",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("review_round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_name", sa.String(64), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_agent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _created(),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_wo_approval_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_wo_approval_reviewer"),
        sa.UniqueConstraint("work_order_id", "review_round", name="uq_wo_approval_round"),
        sa.CheckConstraint("result IN ('approved','rejected')", name="ck_wo_approval_result"),
        sa.CheckConstraint(
            "result <> 'rejected' OR comment IS NOT NULL", name="ck_wo_approval_reject"
        ),
    )
    op.create_index(
        "idx_wo_approval_order", "work_order_approvals", ["work_order_id", "created_at"]
    )
    op.create_index(
        "idx_wo_approval_reviewer",
        "work_order_approvals",
        ["reviewer_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "work_order_attachments",
        _id(),
        sa.Column("work_order_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("file_ext", sa.String(16), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        _created(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_wo_attach_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name="fk_wo_attach_user"),
    )
    op.create_index(
        "idx_wo_attach_order", "work_order_attachments", ["work_order_id", "created_at"]
    )

    # ---------- 通知、配置、日志 ----------
    op.create_table(
        "notifications",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("related_type", sa.String(32), nullable=True),
        sa.Column("related_id", sa.BigInteger(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_notifications_user"),
        sa.CheckConstraint(
            "related_type IS NULL OR related_type IN "
            "('work_order','report','alert','account','system')",
            name="ck_notifications_related_type",
        ),
        sa.CheckConstraint(
            "type IN ('work_order_assigned','work_order_review','work_order_rejected',"
            "'work_order_completed','work_order_recalled','transfer_request','transfer_result',"
            "'account_changed','work_order_overdue','report_published','alert_triggered','system')",
            name="ck_notifications_type",
        ),
    )
    op.create_index(
        "idx_notifications_user",
        "notifications",
        ["user_id", "is_read", sa.text("created_at DESC")],
    )
    op.create_index("idx_notifications_created", "notifications", ["created_at"])

    op.create_table(
        "system_configs",
        _id(),
        sa.Column("config_key", sa.String(128), nullable=False),
        sa.Column("config_value", postgresql.JSONB(), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_system_configs_user"),
        sa.UniqueConstraint("config_key", name="uq_system_configs_key"),
        sa.CheckConstraint(
            "value_type IN ('string','int','decimal','bool','json')", name="ck_configs_value_type"
        ),
        sa.CheckConstraint(
            "category IN ('work_order','inventory','finance','report','agent','security','auth','log')",
            name="ck_configs_category",
        ),
    )
    op.create_index("idx_system_configs_category", "system_configs", ["category"])

    op.create_table(
        "operation_logs",
        _id(),
        sa.Column("log_type", sa.String(16), nullable=False, server_default="operation"),
        sa.Column("log_level", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("user_name_snapshot", sa.String(64), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("resource", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(16), nullable=False, server_default="success"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("sensitive_detail", sa.LargeBinary(), nullable=True),
        _created(),
        sa.CheckConstraint("log_type IN ('operation','agent','system')", name="ck_oplog_type"),
        sa.CheckConstraint("log_level IN ('normal','important','critical')", name="ck_oplog_level"),
        sa.CheckConstraint("result IN ('success','failure','denied')", name="ck_oplog_result"),
    )
    op.create_index("idx_oplog_created", "operation_logs", ["created_at"])
    op.create_index(
        "idx_oplog_user_created", "operation_logs", ["user_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "idx_oplog_dept_created", "operation_logs", ["department_id", sa.text("created_at DESC")]
    )
    op.create_index("idx_oplog_target", "operation_logs", ["resource", "target_type", "target_id"])
    op.create_index(
        "idx_oplog_type_level", "operation_logs", ["log_type", "log_level", "created_at"]
    )

    op.create_table(
        "agent_logs",
        _id(),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("input_summary", sa.String(500), nullable=True),
        sa.Column("output_summary", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        _created(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_agent_logs_user"),
    )
    op.create_index("idx_agentlog_session", "agent_logs", ["session_id", "created_at"])
    op.create_index("idx_agentlog_user", "agent_logs", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_agentlog_created", "agent_logs", ["created_at"])

    # ---------- 单号与账号申请 ----------
    op.create_table(
        "order_no_sequences",
        sa.Column("seq_type", sa.String(8), nullable=False),
        sa.Column("seq_date", sa.Date(), nullable=False),
        sa.Column("current_seq", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("seq_type", "seq_date", name="pk_order_no_sequences"),
        sa.CheckConstraint("seq_type IN ('WO','PO','SO','AC')", name="ck_seq_type"),
    )

    op.create_table(
        "account_change_requests",
        _id(),
        sa.Column("request_no", sa.String(24), nullable=False),
        sa.Column("request_type", sa.String(16), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.String(500), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], name="fk_account_req_target"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name="fk_account_req_requester"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name="fk_account_req_reviewer"),
        sa.CheckConstraint(
            "request_type IN ('open','update','disable')", name="ck_account_req_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')", name="ck_account_req_status"
        ),
    )
    op.create_index("uq_account_req_no", "account_change_requests", ["request_no"], unique=True)
    op.create_index("idx_account_req_status", "account_change_requests", ["status", "created_at"])

    _seed()


def _seed() -> None:
    # 部门
    op.execute(
        """
        INSERT INTO departments (code, name, sort_no) VALUES
          ('hr','人事部',1),
          ('finance','财务部',2),
          ('business','业务部',3),
          ('production','生产部',4),
          ('security','安保岗位',5),
          ('logistics','物流部',6)
        """
    )

    # 岗位
    op.execute(
        """
        INSERT INTO positions (code, name, department_id, data_scope, business_domain) VALUES
          ('general_manager','总经理',NULL,'company',NULL),
          ('hr_head','人事负责人',(SELECT id FROM departments WHERE code='hr'),'company',NULL),
          ('hr_specialist','人事专员',(SELECT id FROM departments WHERE code='hr'),'company',NULL),
          ('finance_head','财务负责人',(SELECT id FROM departments WHERE code='finance'),'company',NULL),
          ('accountant','会计',(SELECT id FROM departments WHERE code='finance'),'company',NULL),
          ('cashier','出纳',(SELECT id FROM departments WHERE code='finance'),'company',NULL),
          ('biz_head','业务负责人',(SELECT id FROM departments WHERE code='business'),'department',NULL),
          ('biz_manager','业务经理',(SELECT id FROM departments WHERE code='business'),'self_and_subordinates',NULL),
          ('salesperson','业务员',(SELECT id FROM departments WHERE code='business'),'self',NULL),
          ('purchaser','采购员',(SELECT id FROM departments WHERE code='business'),'self',NULL),
          ('warehouse_head','仓库负责人',(SELECT id FROM departments WHERE code='business'),'business_domain','inventory'),
          ('document_clerk','制单员',(SELECT id FROM departments WHERE code='business'),'self',NULL),
          ('tally_clerk','理货员',(SELECT id FROM departments WHERE code='business'),'self',NULL),
          ('production_head','生产主任',(SELECT id FROM departments WHERE code='production'),'department',NULL),
          ('production_worker','生产工人',(SELECT id FROM departments WHERE code='production'),'self',NULL),
          ('repairman','维修工',(SELECT id FROM departments WHERE code='production'),'self',NULL),
          ('security_head','保安队长',(SELECT id FROM departments WHERE code='security'),'department',NULL),
          ('guard','保安',(SELECT id FROM departments WHERE code='security'),'self',NULL),
          ('logistics_head','物流负责人',(SELECT id FROM departments WHERE code='logistics'),'department',NULL),
          ('dispatcher','调度员',(SELECT id FROM departments WHERE code='logistics'),'self',NULL),
          ('transporter','运输人员',(SELECT id FROM departments WHERE code='logistics'),'self',NULL)
        """
    )

    # 基础授权：21 个岗位各 5 条
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, v.resource, v.action, v.data_scope
        FROM positions p
        CROSS JOIN (VALUES
          ('work_order','create','self'),
          ('work_order','read','self'),
          ('work_order','update','self'),
          ('work_order_transfer','transfer','self'),
          ('operation_log','read','self')
        ) AS v(resource, action, data_scope)
        """
    )

    # 差异授权
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope, business_domain)
        SELECT p.id, v.resource, v.action, v.data_scope, v.business_domain
        FROM positions p
        JOIN (VALUES
          ('general_manager','work_order','read','company',NULL::text),
          ('general_manager','operation_log','read','company',NULL::text),
          ('general_manager','system_log','read','company',NULL::text),
          ('general_manager','report','read','company',NULL::text),
          ('general_manager','alert','read','company',NULL::text),
          ('general_manager','finance_record','read','company',NULL::text),
          ('general_manager','purchase_order','read','company',NULL::text),
          ('general_manager','sales_order','read','company',NULL::text),
          ('general_manager','inventory','read','company',NULL::text),
          ('general_manager','device','read','company',NULL::text),
          ('general_manager','knowledge_document','read','company',NULL::text),
          ('general_manager','account','read','company',NULL::text),
          ('general_manager','org','read','company',NULL::text),
          ('general_manager','config','config','company',NULL::text),
          ('hr_head','account','create','company',NULL::text),
          ('hr_head','account','update','company',NULL::text),
          ('hr_head','account','read','company',NULL::text),
          ('hr_head','account','approve','company',NULL::text),
          ('hr_head','org','create','company',NULL::text),
          ('hr_head','org','update','company',NULL::text),
          ('hr_head','org','read','company',NULL::text),
          ('hr_head','config','config','company',NULL::text),
          ('hr_head','operation_log','read','department',NULL::text),
          ('hr_head','system_log','read','company',NULL::text),
          ('hr_specialist','account','create','company',NULL::text),
          ('hr_specialist','account','update','company',NULL::text),
          ('hr_specialist','account','read','company',NULL::text),
          ('hr_specialist','org','create','company',NULL::text),
          ('hr_specialist','org','update','company',NULL::text),
          ('hr_specialist','org','read','company',NULL::text),
          ('finance_head','work_order','read','company',NULL::text),
          ('finance_head','work_order_review','review','company',NULL::text),
          ('finance_head','finance_record','read','company',NULL::text),
          ('finance_head','finance_record','approve','company',NULL::text),
          ('finance_head','alert','read','company',NULL::text),
          ('finance_head','config','config','company',NULL::text),
          ('finance_head','operation_log','read','department',NULL::text),
          ('accountant','finance_record','create','self',NULL::text),
          ('accountant','finance_record','update','self',NULL::text),
          ('accountant','finance_record','read','company',NULL::text),
          ('cashier','finance_record','create','self',NULL::text),
          ('cashier','finance_record','update','self',NULL::text),
          ('cashier','finance_record','read','company',NULL::text),
          ('biz_head','work_order','read','department',NULL::text),
          ('biz_head','work_order_assign','assign','department',NULL::text),
          ('biz_head','purchase_order','review','department',NULL::text),
          ('biz_head','purchase_order','read','department',NULL::text),
          ('biz_head','sales_order','review','department',NULL::text),
          ('biz_head','sales_order','read','department',NULL::text),
          ('biz_head','customer','read','department',NULL::text),
          ('biz_head','supplier','read','department',NULL::text),
          ('biz_head','operation_log','read','department',NULL::text),
          ('biz_manager','work_order','create','self_and_subordinates',NULL::text),
          ('biz_manager','work_order','read','self_and_subordinates',NULL::text),
          ('biz_manager','sales_order','create','self_and_subordinates',NULL::text),
          ('biz_manager','sales_order','read','self_and_subordinates',NULL::text),
          ('biz_manager','customer','create','self_and_subordinates',NULL::text),
          ('biz_manager','customer','read','self_and_subordinates',NULL::text),
          ('salesperson','sales_order','create','self',NULL::text),
          ('salesperson','sales_order','read','self',NULL::text),
          ('salesperson','customer','create','self',NULL::text),
          ('salesperson','customer','read','self',NULL::text),
          ('purchaser','purchase_order','create','self',NULL::text),
          ('purchaser','purchase_order','read','self',NULL::text),
          ('purchaser','supplier','read','self',NULL::text),
          ('warehouse_head','inventory','read','business_domain','inventory'),
          ('warehouse_head','inventory','update','business_domain','inventory'),
          ('warehouse_head','inventory','approve','business_domain','inventory'),
          ('document_clerk','inventory','create','self',NULL::text),
          ('document_clerk','inventory','read','self',NULL::text),
          ('document_clerk','inventory','update','self',NULL::text),
          ('tally_clerk','inventory','create','self',NULL::text),
          ('tally_clerk','inventory','read','self',NULL::text),
          ('production_head','work_order','read','department',NULL::text),
          ('production_head','work_order_assign','assign','department',NULL::text),
          ('production_head','work_order_review','review','department',NULL::text),
          ('production_head','device','read','department',NULL::text),
          ('production_head','device','update','department',NULL::text),
          ('production_head','config','config','company',NULL::text),
          ('production_head','operation_log','read','department',NULL::text),
          ('production_worker','device','read','department',NULL::text),
          ('repairman','device','read','department',NULL::text),
          ('repairman','device','update','department',NULL::text),
          ('security_head','work_order','read','department',NULL::text),
          ('security_head','work_order_assign','assign','department',NULL::text),
          ('security_head','work_order_review','review','department',NULL::text),
          ('security_head','config','config','company',NULL::text),
          ('security_head','operation_log','read','department',NULL::text),
          ('logistics_head','work_order','read','department',NULL::text),
          ('logistics_head','work_order_assign','assign','department',NULL::text),
          ('logistics_head','work_order_review','review','department',NULL::text),
          ('logistics_head','config','config','company',NULL::text),
          ('logistics_head','operation_log','read','department',NULL::text)
        ) AS v(pos_code, resource, action, data_scope, business_domain)
          ON v.pos_code = p.code
        """
    )

    # 工单类别
    op.execute(
        """
        INSERT INTO work_order_categories (code, name, sort_no) VALUES
          ('device_repair','设备维修',10),
          ('expense_reimbursement','报销',20),
          ('security_patrol','安全巡查',30),
          ('transport_exception','运输异常',40)
        """
    )

    # 系统配置
    op.execute(
        """
        INSERT INTO system_configs (config_key, config_value, value_type, category, description) VALUES
          ('work_order.due_hours.device_repair','24','int','work_order','设备维修默认处理期限（小时）'),
          ('work_order.due_hours.expense_reimbursement','72','int','work_order','报销默认处理期限（小时）'),
          ('work_order.due_hours.security_patrol','8','int','work_order','安全巡查默认处理期限（小时）'),
          ('work_order.due_hours.transport_exception','24','int','work_order','运输异常默认处理期限（小时）'),
          ('work_order.repeat.period_days','30','int','work_order','重复问题统计周期（天）'),
          ('work_order.order_no.prefix','"WO"','string','work_order','工单号前缀'),
          ('work_order.overdue.scan_interval_minutes','5','int','work_order','超时扫描间隔（分钟）'),
          ('work_order.overdue.enabled','true','bool','work_order','是否启用超时标记'),
          ('work_order.attachment.max_size_mb','20','int','work_order','附件大小上限（MB）'),
          ('agent.tool.timeout_seconds','5','int','agent','工具调用超时（秒）'),
          ('agent.tool.max_retries','1','int','agent','工具调用重试次数'),
          ('agent.confirm.ttl_seconds','300','int','agent','写操作确认令牌有效期（秒）'),
          ('log.retention.operation_normal_days','180','int','log','普通操作日志保留期'),
          ('log.retention.operation_important_days','730','int','log','重要操作日志保留期'),
          ('log.retention.operation_critical_days','1095','int','log','关键操作日志保留期'),
          ('log.retention.agent_days','90','int','log','Agent 日志保留期'),
          ('log.retention.voice_days','7','int','log','语音文件保留期'),
          ('auth.access_token_minutes','120','int','auth','access token 有效期（分钟）'),
          ('auth.refresh_token_days','7','int','auth','refresh token 有效期（天）')
        """
    )


def downgrade() -> None:
    op.drop_table("account_change_requests")
    op.drop_table("order_no_sequences")
    op.drop_table("agent_logs")
    op.drop_table("operation_logs")
    op.drop_table("system_configs")
    op.drop_table("notifications")
    op.drop_table("work_order_attachments")
    op.drop_table("work_order_approvals")
    op.drop_table("work_order_records")
    op.drop_table("work_order_transport")
    op.drop_table("work_order_patrol")
    op.drop_table("work_order_expense")
    op.drop_table("work_order_device")
    op.drop_table("work_orders")
    op.drop_table("work_order_categories")
    op.drop_table("devices")
    op.drop_table("position_permissions")
    op.drop_table("user_positions")
    op.drop_table("users")
    op.drop_table("positions")
    op.drop_table("departments")
