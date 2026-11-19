"""V2 种子：岗位权限按 V2 规则重算、知识库配置、默认仓库

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 制单员、理货员的数据范围按 V2 改为本部门
    op.execute(
        """
        UPDATE positions SET data_scope = 'department'
        WHERE code IN ('document_clerk','tally_clerk')
        """
    )

    # 权限以 V2 规则为准整体重算（V1 种子中的旧范围/动作一并纠正）
    op.execute("DELETE FROM position_permissions")

    # 基础授权：21 个岗位各 6 条
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
          ('operation_log','read','self'),
          ('knowledge_document','read','company')
        ) AS v(resource, action, data_scope)
        """
    )

    # 差异授权：多岗位取并集、多条取最大范围（服务层按类别/键前缀二次限制）
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope, business_domain)
        SELECT p.id, v.resource, v.action, v.data_scope, v.business_domain
        FROM positions p
        JOIN (VALUES
          -- 总经理
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
          ('general_manager','supplier','read','company',NULL::text),
          ('general_manager','customer','read','company',NULL::text),
          ('general_manager','product','read','company',NULL::text),
          ('general_manager','account','read','company',NULL::text),
          ('general_manager','org','read','company',NULL::text),
          ('general_manager','config','config','company',NULL::text),
          -- 人事负责人
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
          ('hr_head','knowledge_document','create','company',NULL::text),
          ('hr_head','knowledge_document','update','company',NULL::text),
          ('hr_head','knowledge_document','delete','company',NULL::text),
          ('hr_head','knowledge_document','read','department',NULL::text),
          -- 人事专员
          ('hr_specialist','account','create','company',NULL::text),
          ('hr_specialist','account','update','company',NULL::text),
          ('hr_specialist','account','read','company',NULL::text),
          ('hr_specialist','org','create','company',NULL::text),
          ('hr_specialist','org','update','company',NULL::text),
          ('hr_specialist','org','read','company',NULL::text),
          ('hr_specialist','knowledge_document','create','company',NULL::text),
          ('hr_specialist','knowledge_document','update','company',NULL::text),
          ('hr_specialist','knowledge_document','delete','company',NULL::text),
          ('hr_specialist','knowledge_document','read','department',NULL::text),
          -- 财务负责人
          ('finance_head','work_order','read','company',NULL::text),
          ('finance_head','work_order_review','review','company',NULL::text),
          ('finance_head','finance_record','read','company',NULL::text),
          ('finance_head','finance_record','review','company',NULL::text),
          ('finance_head','alert','read','company',NULL::text),
          ('finance_head','config','config','company',NULL::text),
          ('finance_head','operation_log','read','department',NULL::text),
          ('finance_head','knowledge_document','create','department',NULL::text),
          ('finance_head','knowledge_document','update','department',NULL::text),
          ('finance_head','knowledge_document','delete','department',NULL::text),
          ('finance_head','knowledge_document','read','department',NULL::text),
          -- 会计
          ('accountant','finance_record','create','company',NULL::text),
          ('accountant','finance_record','read','company',NULL::text),
          -- 出纳
          ('cashier','finance_record','create','company',NULL::text),
          ('cashier','finance_record','read','company',NULL::text),
          -- 业务负责人
          ('biz_head','work_order','read','department',NULL::text),
          ('biz_head','work_order_assign','assign','department',NULL::text),
          ('biz_head','purchase_order','review','company',NULL::text),
          ('biz_head','purchase_order','read','company',NULL::text),
          ('biz_head','sales_order','review','company',NULL::text),
          ('biz_head','sales_order','read','company',NULL::text),
          ('biz_head','customer','read','company',NULL::text),
          ('biz_head','supplier','read','company',NULL::text),
          ('biz_head','product','read','company',NULL::text),
          ('biz_head','inventory','read','company',NULL::text),
          ('biz_head','operation_log','read','department',NULL::text),
          ('biz_head','knowledge_document','create','department',NULL::text),
          ('biz_head','knowledge_document','update','department',NULL::text),
          ('biz_head','knowledge_document','delete','department',NULL::text),
          ('biz_head','knowledge_document','read','department',NULL::text),
          -- 业务经理
          ('biz_manager','work_order','create','self_and_subordinates',NULL::text),
          ('biz_manager','work_order','read','self_and_subordinates',NULL::text),
          ('biz_manager','sales_order','create','department',NULL::text),
          ('biz_manager','sales_order','read','department',NULL::text),
          ('biz_manager','customer','create','department',NULL::text),
          ('biz_manager','customer','update','department',NULL::text),
          ('biz_manager','customer','read','department',NULL::text),
          ('biz_manager','product','create','company',NULL::text),
          ('biz_manager','product','update','company',NULL::text),
          ('biz_manager','product','read','company',NULL::text),
          ('biz_manager','inventory','read','department',NULL::text),
          -- 业务员
          ('salesperson','sales_order','create','self',NULL::text),
          ('salesperson','sales_order','read','self',NULL::text),
          ('salesperson','customer','create','self',NULL::text),
          ('salesperson','customer','update','self',NULL::text),
          ('salesperson','customer','read','self',NULL::text),
          ('salesperson','product','read','company',NULL::text),
          -- 采购员
          ('purchaser','purchase_order','create','self',NULL::text),
          ('purchaser','purchase_order','read','self',NULL::text),
          ('purchaser','supplier','create','self',NULL::text),
          ('purchaser','supplier','update','self',NULL::text),
          ('purchaser','supplier','read','self',NULL::text),
          ('purchaser','product','read','company',NULL::text),
          -- 仓库负责人
          ('warehouse_head','inventory','read','business_domain','inventory'),
          ('warehouse_head','inventory','review','business_domain','inventory'),
          -- 制单员 / 理货员
          ('document_clerk','inventory','create','department',NULL::text),
          ('document_clerk','inventory','read','department',NULL::text),
          ('document_clerk','inventory','update','department',NULL::text),
          ('tally_clerk','inventory','create','department',NULL::text),
          ('tally_clerk','inventory','read','department',NULL::text),
          ('tally_clerk','inventory','update','department',NULL::text),
          -- 生产主任
          ('production_head','work_order','read','department',NULL::text),
          ('production_head','work_order_assign','assign','department',NULL::text),
          ('production_head','work_order_review','review','department',NULL::text),
          ('production_head','device','read','department',NULL::text),
          ('production_head','device','update','department',NULL::text),
          ('production_head','config','config','company',NULL::text),
          ('production_head','operation_log','read','department',NULL::text),
          ('production_head','knowledge_document','create','department',NULL::text),
          ('production_head','knowledge_document','update','department',NULL::text),
          ('production_head','knowledge_document','delete','department',NULL::text),
          ('production_head','knowledge_document','read','department',NULL::text),
          -- 生产工人
          ('production_worker','device','read','department',NULL::text),
          -- 维修工
          ('repairman','device','read','department',NULL::text),
          ('repairman','device','update','department',NULL::text),
          -- 保安队长
          ('security_head','work_order','read','department',NULL::text),
          ('security_head','work_order_assign','assign','department',NULL::text),
          ('security_head','work_order_review','review','department',NULL::text),
          ('security_head','config','config','company',NULL::text),
          ('security_head','operation_log','read','department',NULL::text),
          ('security_head','knowledge_document','create','department',NULL::text),
          ('security_head','knowledge_document','update','department',NULL::text),
          ('security_head','knowledge_document','delete','department',NULL::text),
          ('security_head','knowledge_document','read','department',NULL::text),
          -- 物流负责人
          ('logistics_head','work_order','read','department',NULL::text),
          ('logistics_head','work_order_assign','assign','department',NULL::text),
          ('logistics_head','work_order_review','review','department',NULL::text),
          ('logistics_head','config','config','company',NULL::text),
          ('logistics_head','operation_log','read','department',NULL::text),
          ('logistics_head','knowledge_document','create','department',NULL::text),
          ('logistics_head','knowledge_document','update','department',NULL::text),
          ('logistics_head','knowledge_document','delete','department',NULL::text),
          ('logistics_head','knowledge_document','read','department',NULL::text)
        ) AS v(pos_code, resource, action, data_scope, business_domain)
          ON v.pos_code = p.code
        """
    )

    # 知识库配置（幂等）
    op.execute(
        """
        INSERT INTO system_configs (config_key, config_value, value_type, category, description)
        VALUES
          ('knowledge.document.max_size_mb','50','int','knowledge','单个知识文档上限 MB'),
          ('knowledge.ocr.min_chars_per_page','50','int','knowledge','每页字符低于此值视为扫描件'),
          ('knowledge.chunk.size','600','int','knowledge','分块目标字符数'),
          ('knowledge.chunk.overlap','100','int','knowledge','相邻块重叠字符数'),
          ('knowledge.retrieval.top_k','8','int','knowledge','召回块数上限'),
          ('knowledge.retrieval.min_score','0.25','decimal','knowledge','余弦相似度下限'),
          ('knowledge.context.max_chars','6000','int','knowledge','单次注入模型的最大字符数'),
          ('embedding.batch_size','16','int','knowledge','向量化批大小')
        ON CONFLICT (config_key) DO NOTHING
        """
    )

    # 默认仓库
    op.execute(
        """
        INSERT INTO warehouses (code, name, address, is_active, is_mock)
        SELECT 'WH01','主仓','厂区一号仓',true,false
        WHERE NOT EXISTS (
          SELECT 1 FROM warehouses WHERE code = 'WH01' AND deleted_at IS NULL
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_configs WHERE config_key LIKE 'knowledge.%' OR config_key = 'embedding.batch_size'"
    )
    op.execute(
        """
        DELETE FROM warehouses
        WHERE code = 'WH01'
          AND NOT EXISTS (SELECT 1 FROM inventory WHERE inventory.warehouse_id = warehouses.id)
          AND NOT EXISTS (
            SELECT 1 FROM stock_movements WHERE stock_movements.warehouse_id = warehouses.id
          )
        """
    )
    op.execute(
        """
        UPDATE positions SET data_scope = 'self'
        WHERE code IN ('document_clerk','tally_clerk')
        """
    )
