"""V2 业务表：主数据、采购/销售、库存、财务

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_STATUS = "('draft','pending_review','approved','rejected','void')"
MOVEMENT_STATUS = "('draft','pending_execute','pending_review','approved','rejected','void')"
CHECK_STATUS = "('draft','pending_review','approved','rejected','void')"
MOVEMENT_TYPES = "('inbound','outbound','stocktake_in','stocktake_out','loss')"
MOVEMENT_SOURCES = "('purchase_order','sales_order','stock_check','manual')"
FINANCE_TYPES = "('income','cost','expense','receivable','payable')"
FINANCE_SOURCES = "('sales_order','purchase_order','stock_movement','work_order','manual')"


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


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def _is_mock() -> sa.Column:
    return sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.text("false"))


def _version() -> sa.Column:
    return sa.Column("version", sa.Integer(), nullable=False, server_default="0")


def _deleted() -> sa.Column:
    return sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    # ---------- V1 表增量 ----------
    op.add_column("work_orders", _is_mock())
    op.drop_constraint("ck_configs_category", "system_configs", type_="check")
    op.create_check_constraint(
        "ck_configs_category",
        "system_configs",
        "category IN ('work_order','inventory','finance','report','agent','security','auth','log',"
        "'knowledge')",
    )
    op.drop_constraint("ck_seq_type", "order_no_sequences", type_="check")
    op.create_check_constraint(
        "ck_seq_type",
        "order_no_sequences",
        "seq_type IN ('WO','PO','SO','AC','SM','SC','FR','CF')",
    )

    # ---------- 主数据 ----------
    op.create_table(
        "warehouses",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _is_mock(),
        *_audit(),
        _deleted(),
    )
    op.create_index(
        "uq_warehouses_code",
        "warehouses",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "customers",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("credit_limit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        _is_mock(),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_customers_owner"),
        sa.CheckConstraint("credit_limit >= 0", name="ck_customers_credit"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_customers_status"),
    )
    op.create_index(
        "uq_customers_code",
        "customers",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_customers_owner", "customers", ["owner_id"])

    op.create_table(
        "suppliers",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("payment_type", sa.String(16), nullable=False, server_default="cash"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        _is_mock(),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_suppliers_owner"),
        sa.CheckConstraint("payment_type IN ('cash','credit')", name="ck_suppliers_payment"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_suppliers_status"),
    )
    op.create_index(
        "uq_suppliers_code",
        "suppliers",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_suppliers_owner", "suppliers", ["owner_id"])

    op.create_table(
        "products",
        _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("spec", sa.String(128), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("purchase_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("sale_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        _is_mock(),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_products_owner"),
        sa.CheckConstraint("purchase_price >= 0", name="ck_products_purchase_price"),
        sa.CheckConstraint("sale_price >= 0", name="ck_products_sale_price"),
    )
    op.create_index(
        "uq_products_code",
        "products",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_products_category", "products", ["category"])

    # ---------- 采购 / 销售 ----------
    op.create_table(
        "purchase_orders",
        _id(),
        sa.Column("order_no", sa.String(20), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("purchaser_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name="fk_purchase_orders_supplier"
        ),
        sa.ForeignKeyConstraint(
            ["purchaser_id"], ["users.id"], name="fk_purchase_orders_purchaser"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_purchase_orders_department"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_purchase_orders_reviewer"),
        sa.CheckConstraint(f"status IN {ORDER_STATUS}", name="ck_po_status"),
        sa.CheckConstraint("total_amount >= 0", name="ck_po_total"),
        sa.CheckConstraint(
            "expected_date IS NULL OR expected_date >= order_date", name="ck_po_dates"
        ),
        sa.CheckConstraint("version >= 0", name="ck_po_version"),
    )
    op.create_index(
        "uq_purchase_orders_order_no",
        "purchase_orders",
        ["order_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_po_department_status",
        "purchase_orders",
        ["department_id", "status", sa.text("order_date DESC")],
    )

    op.create_table(
        "purchase_order_items",
        _id(),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name="fk_purchase_order_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_purchase_order_items_product"
        ),
        sa.UniqueConstraint("purchase_order_id", "line_no", name="uq_purchase_order_items_line"),
        sa.CheckConstraint("line_no > 0", name="ck_po_items_line"),
        sa.CheckConstraint("quantity > 0", name="ck_po_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_po_items_price"),
        sa.CheckConstraint("amount >= 0", name="ck_po_items_amount"),
    )

    op.create_table(
        "sales_orders",
        _id(),
        sa.Column("order_no", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("salesperson_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_sales_orders_customer"),
        sa.ForeignKeyConstraint(
            ["salesperson_id"], ["users.id"], name="fk_sales_orders_salesperson"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_sales_orders_department"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_sales_orders_reviewer"),
        sa.CheckConstraint(f"status IN {ORDER_STATUS}", name="ck_so_status"),
        sa.CheckConstraint("total_amount >= 0", name="ck_so_total"),
        sa.CheckConstraint("version >= 0", name="ck_so_version"),
    )
    op.create_index(
        "uq_sales_orders_order_no",
        "sales_orders",
        ["order_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_so_department_status",
        "sales_orders",
        ["department_id", "status", sa.text("order_date DESC")],
    )

    op.create_table(
        "sales_order_items",
        _id(),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], ["sales_orders.id"], name="fk_sales_order_items_order"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_sales_order_items_product"
        ),
        sa.UniqueConstraint("sales_order_id", "line_no", name="uq_sales_order_items_line"),
        sa.CheckConstraint("line_no > 0", name="ck_so_items_line"),
        sa.CheckConstraint("quantity > 0", name="ck_so_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_so_items_price"),
        sa.CheckConstraint("amount >= 0", name="ck_so_items_amount"),
    )

    # ---------- 库存 ----------
    op.create_table(
        "inventory",
        _id(),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False, server_default="0"),
        *_audit(),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_inventory_warehouse"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_inventory_product"),
        sa.UniqueConstraint("warehouse_id", "product_id", name="uq_inventory_warehouse_product"),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_quantity"),
    )

    op.create_table(
        "stock_movements",
        _id(),
        sa.Column("movement_no", sa.String(24), nullable=False),
        sa.Column("movement_type", sa.String(16), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("executor_id", sa.BigInteger(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], name="fk_stock_movements_warehouse"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_stock_movements_department"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stock_movements_creator"),
        sa.ForeignKeyConstraint(["executor_id"], ["users.id"], name="fk_stock_movements_executor"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_stock_movements_reviewer"),
        sa.CheckConstraint(f"movement_type IN {MOVEMENT_TYPES}", name="ck_sm_type"),
        sa.CheckConstraint(f"source_type IN {MOVEMENT_SOURCES}", name="ck_sm_source"),
        sa.CheckConstraint(f"status IN {MOVEMENT_STATUS}", name="ck_sm_status"),
        sa.CheckConstraint("version >= 0", name="ck_sm_version"),
    )
    op.create_index(
        "uq_stock_movements_movement_no",
        "stock_movements",
        ["movement_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_sm_warehouse_status", "stock_movements", ["warehouse_id", "status", "created_at"]
    )
    op.create_index("idx_sm_source", "stock_movements", ["source_type", "source_id"])

    op.create_table(
        "stock_movement_items",
        _id(),
        sa.Column("movement_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("before_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("after_quantity", sa.Numeric(14, 3), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["stock_movements.id"], name="fk_stock_movement_items_movement"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_stock_movement_items_product"
        ),
        sa.UniqueConstraint("movement_id", "line_no", name="uq_stock_movement_items_line"),
        sa.CheckConstraint("line_no > 0", name="ck_sm_items_line"),
        sa.CheckConstraint("quantity > 0", name="ck_sm_items_quantity"),
        sa.CheckConstraint(
            "before_quantity IS NULL OR before_quantity >= 0", name="ck_sm_items_before"
        ),
        sa.CheckConstraint(
            "after_quantity IS NULL OR after_quantity >= 0", name="ck_sm_items_after"
        ),
    )

    op.create_table(
        "stock_checks",
        _id(),
        sa.Column("check_no", sa.String(24), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("check_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], name="fk_stock_checks_warehouse"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_stock_checks_department"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stock_checks_creator"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_stock_checks_reviewer"),
        sa.CheckConstraint(f"status IN {CHECK_STATUS}", name="ck_sc_status"),
        sa.CheckConstraint("version >= 0", name="ck_sc_version"),
    )
    op.create_index(
        "uq_stock_checks_check_no",
        "stock_checks",
        ["check_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "stock_check_items",
        _id(),
        sa.Column("check_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("book_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("actual_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("diff_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("remark", sa.String(200), nullable=True),
        *_audit(),
        sa.ForeignKeyConstraint(
            ["check_id"], ["stock_checks.id"], name="fk_stock_check_items_check"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_stock_check_items_product"
        ),
        sa.UniqueConstraint("check_id", "product_id", name="uq_stock_check_items_product"),
        sa.CheckConstraint("book_quantity >= 0", name="ck_sc_items_book"),
        sa.CheckConstraint("actual_quantity >= 0", name="ck_sc_items_actual"),
    )

    # ---------- 财务 ----------
    op.create_table(
        "finance_records",
        _id(),
        sa.Column("record_no", sa.String(24), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("accounting_period", sa.String(7), nullable=False),
        sa.Column("counterparty_type", sa.String(16), nullable=False, server_default="none"),
        sa.Column("counterparty_id", sa.BigInteger(), nullable=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("account_subject", sa.String(64), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_finance_records_department"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_finance_records_creator"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_finance_records_reviewer"),
        sa.CheckConstraint(f"record_type IN {FINANCE_TYPES}", name="ck_fin_type"),
        sa.CheckConstraint(
            "counterparty_type IN ('customer','supplier','none')", name="ck_fin_counterparty"
        ),
        sa.CheckConstraint(f"source_type IN {FINANCE_SOURCES}", name="ck_fin_source"),
        sa.CheckConstraint(f"status IN {ORDER_STATUS}", name="ck_fin_status"),
        sa.CheckConstraint("amount >= 0", name="ck_fin_amount"),
        sa.CheckConstraint("version >= 0", name="ck_fin_version"),
    )
    op.create_index("idx_fin_date_type", "finance_records", ["record_date", "record_type"])
    op.create_index("idx_fin_status_period", "finance_records", ["status", "accounting_period"])
    op.create_index("idx_fin_source", "finance_records", ["source_type", "source_id"])
    op.create_index(
        "uq_finance_source",
        "finance_records",
        ["source_type", "source_id", "record_type"],
        unique=True,
        postgresql_where=sa.text(
            "source_id IS NOT NULL AND status <> 'void' AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "cash_flows",
        _id(),
        sa.Column("flow_no", sa.String(24), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("flow_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(32), nullable=True),
        sa.Column("related_order_type", sa.String(16), nullable=True),
        sa.Column("related_order_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        _version(),
        _is_mock(),
        sa.Column("remark", sa.String(500), nullable=True),
        *_audit(),
        _deleted(),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_cash_flows_department"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_cash_flows_creator"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_cash_flows_reviewer"),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_cf_direction"),
        sa.CheckConstraint(
            "related_order_type IS NULL OR related_order_type IN ('sales_order','purchase_order')",
            name="ck_cf_related_type",
        ),
        sa.CheckConstraint(f"status IN {ORDER_STATUS}", name="ck_cf_status"),
        sa.CheckConstraint("amount > 0", name="ck_cf_amount"),
        sa.CheckConstraint("version >= 0", name="ck_cf_version"),
    )
    op.create_index(
        "uq_cash_flows_flow_no",
        "cash_flows",
        ["flow_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_cf_date_direction", "cash_flows", ["flow_date", "direction"])
    op.create_index("idx_cf_related", "cash_flows", ["related_order_type", "related_order_id"])


def downgrade() -> None:
    op.drop_index("idx_cf_related", table_name="cash_flows")
    op.drop_index("idx_cf_date_direction", table_name="cash_flows")
    op.drop_index("uq_cash_flows_flow_no", table_name="cash_flows")
    op.drop_table("cash_flows")

    op.drop_index("uq_finance_source", table_name="finance_records")
    op.drop_index("idx_fin_source", table_name="finance_records")
    op.drop_index("idx_fin_status_period", table_name="finance_records")
    op.drop_index("idx_fin_date_type", table_name="finance_records")
    op.drop_table("finance_records")

    op.drop_table("stock_check_items")
    op.drop_index("uq_stock_checks_check_no", table_name="stock_checks")
    op.drop_table("stock_checks")
    op.drop_table("stock_movement_items")
    op.drop_index("idx_sm_source", table_name="stock_movements")
    op.drop_index("idx_sm_warehouse_status", table_name="stock_movements")
    op.drop_index("uq_stock_movements_movement_no", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("inventory")

    op.drop_table("sales_order_items")
    op.drop_index("idx_so_department_status", table_name="sales_orders")
    op.drop_index("uq_sales_orders_order_no", table_name="sales_orders")
    op.drop_table("sales_orders")
    op.drop_table("purchase_order_items")
    op.drop_index("idx_po_department_status", table_name="purchase_orders")
    op.drop_index("uq_purchase_orders_order_no", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("idx_products_category", table_name="products")
    op.drop_index("uq_products_code", table_name="products")
    op.drop_table("products")
    op.drop_index("idx_suppliers_owner", table_name="suppliers")
    op.drop_index("uq_suppliers_code", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index("idx_customers_owner", table_name="customers")
    op.drop_index("uq_customers_code", table_name="customers")
    op.drop_table("customers")
    op.drop_index("uq_warehouses_code", table_name="warehouses")
    op.drop_table("warehouses")

    op.drop_constraint("ck_seq_type", "order_no_sequences", type_="check")
    op.create_check_constraint(
        "ck_seq_type",
        "order_no_sequences",
        "seq_type IN ('WO','PO','SO','AC')",
    )
    op.drop_constraint("ck_configs_category", "system_configs", type_="check")
    op.create_check_constraint(
        "ck_configs_category",
        "system_configs",
        "category IN ('work_order','inventory','finance','report','agent','security','auth','log')",
    )
    op.drop_column("work_orders", "is_mock")
