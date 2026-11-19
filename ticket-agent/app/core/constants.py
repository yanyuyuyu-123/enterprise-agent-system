"""固定业务规则常量。

可调参数（期限小时数、重复问题周期等）读 `system_configs`，不写在这里。
类别→岗位映射来自《规划方案》4.1.1、12.16，调整需同步文档。
"""

# 工单状态
STATUS_SUPPLEMENTING = "supplementing"
STATUS_PENDING_ASSIGNMENT = "pending_assignment"
STATUS_PENDING_PROCESS = "pending_process"
STATUS_PROCESSING = "processing"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_REJECTED = "rejected"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES: tuple[str, ...] = (
    STATUS_SUPPLEMENTING,
    STATUS_PENDING_ASSIGNMENT,
    STATUS_PENDING_PROCESS,
    STATUS_PROCESSING,
    STATUS_PENDING_REVIEW,
    STATUS_REJECTED,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)

# 可撤回状态：仅待分配、待处理（规划 4.1.2、12.16）
RECALLABLE_STATUSES: tuple[str, ...] = (STATUS_PENDING_ASSIGNMENT, STATUS_PENDING_PROCESS)

# 超时扫描范围
OVERDUE_SCAN_STATUSES: tuple[str, ...] = (
    STATUS_PENDING_PROCESS,
    STATUS_PROCESSING,
    STATUS_PENDING_REVIEW,
)

# 四类工单
CATEGORY_DEVICE_REPAIR = "device_repair"
CATEGORY_EXPENSE_REIMBURSEMENT = "expense_reimbursement"
CATEGORY_SECURITY_PATROL = "security_patrol"
CATEGORY_TRANSPORT_EXCEPTION = "transport_exception"

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_DEVICE_REPAIR,
    CATEGORY_EXPENSE_REIMBURSEMENT,
    CATEGORY_SECURITY_PATROL,
    CATEGORY_TRANSPORT_EXCEPTION,
)

# 创建人岗位；None 表示不限岗位
CATEGORY_CREATOR_POSITIONS: dict[str, frozenset[str] | None] = {
    CATEGORY_DEVICE_REPAIR: frozenset({"production_worker", "repairman"}),
    CATEGORY_EXPENSE_REIMBURSEMENT: None,
    CATEGORY_SECURITY_PATROL: frozenset({"guard"}),
    CATEGORY_TRANSPORT_EXCEPTION: frozenset({"transporter", "dispatcher"}),
}

# 处理人岗位；报销为创建人本人，None 表示由单据决定
CATEGORY_ASSIGNEE_POSITIONS: dict[str, frozenset[str] | None] = {
    CATEGORY_DEVICE_REPAIR: frozenset({"repairman"}),
    CATEGORY_EXPENSE_REIMBURSEMENT: None,
    CATEGORY_SECURITY_PATROL: frozenset({"guard"}),
    CATEGORY_TRANSPORT_EXCEPTION: frozenset({"transporter"}),
}

# 分配人岗位；报销无分配环节
CATEGORY_ASSIGNER_POSITION: dict[str, str | None] = {
    CATEGORY_DEVICE_REPAIR: "production_head",
    CATEGORY_EXPENSE_REIMBURSEMENT: None,
    CATEGORY_SECURITY_PATROL: "security_head",
    CATEGORY_TRANSPORT_EXCEPTION: "logistics_head",
}

# 审核人岗位，单级审核
CATEGORY_REVIEWER_POSITION: dict[str, str] = {
    CATEGORY_DEVICE_REPAIR: "production_head",
    CATEGORY_EXPENSE_REIMBURSEMENT: "finance_head",
    CATEGORY_SECURITY_PATROL: "security_head",
    CATEGORY_TRANSPORT_EXCEPTION: "logistics_head",
}

# 类别 → 明细表模型名，建单/补充时同事务写入
CATEGORY_DETAIL_TABLE: dict[str, str] = {
    CATEGORY_DEVICE_REPAIR: "work_order_device",
    CATEGORY_EXPENSE_REIMBURSEMENT: "work_order_expense",
    CATEGORY_SECURITY_PATROL: "work_order_patrol",
    CATEGORY_TRANSPORT_EXCEPTION: "work_order_transport",
}

# 类别 → 期限配置键
CATEGORY_DUE_HOURS_CONFIG: dict[str, str] = {
    CATEGORY_DEVICE_REPAIR: "work_order.due_hours.device_repair",
    CATEGORY_EXPENSE_REIMBURSEMENT: "work_order.due_hours.expense_reimbursement",
    CATEGORY_SECURITY_PATROL: "work_order.due_hours.security_patrol",
    CATEGORY_TRANSPORT_EXCEPTION: "work_order.due_hours.transport_exception",
}

# 通用数据范围（business_domain 为业务域例外，不算第五种）
SCOPE_COMPANY = "company"
SCOPE_DEPARTMENT = "department"
SCOPE_SELF_AND_SUBORDINATES = "self_and_subordinates"
SCOPE_SELF = "self"
SCOPE_BUSINESS_DOMAIN = "business_domain"

SCOPE_ORDER: dict[str, int] = {
    SCOPE_SELF: 1,
    SCOPE_SELF_AND_SUBORDINATES: 2,
    SCOPE_DEPARTMENT: 3,
    SCOPE_COMPANY: 4,
}

# 知识文档分类，与 knowledge_documents.ck_kd_category 约束保持一致
KNOWLEDGE_CATEGORIES: tuple[str, ...] = (
    "contract",
    "policy",
    "manual",
    "quotation",
    "process",
    "other",
)

BUSINESS_DOMAINS: tuple[str, ...] = (
    "inventory",
    "finance",
    "hr",
    "sales",
    "purchase",
    "production",
    "security",
    "logistics",
)

# 出纳只录资金流水：仅持出纳岗位的账号不能新增财务记录
FINANCE_RECORD_CREATOR_POSITIONS: tuple[str, ...] = (
    "accountant",
    "finance_head",
    "general_manager",
)

# 权限动作
ACTIONS: tuple[str, ...] = (
    "create",
    "read",
    "update",
    "delete",
    "assign",
    "review",
    "transfer",
    "approve",
    "export",
    "config",
)

# 权限资源
RESOURCES: tuple[str, ...] = (
    "work_order",
    "work_order_assign",
    "work_order_review",
    "work_order_transfer",
    "report",
    "knowledge_document",
    "operation_log",
    "system_log",
    "account",
    "org",
    "device",
    "purchase_order",
    "sales_order",
    "customer",
    "supplier",
    "product",
    "inventory",
    "finance_record",
    "config",
    "alert",
    "voice",
    "safe_stock",
)
