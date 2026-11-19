"""V3 种子：语音/报告/预警/安全库存配置与岗位授权

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_configs (config_key, config_value, value_type, category, description)
        VALUES
          ('voice.record.max_duration_seconds','60','int','voice','单次录音时长上限'),
          ('voice.file.max_size_mb','10','int','voice','语音文件大小上限'),
          ('voice.asr.model','"sensevoice-small-int8"','string','voice','本地识别模型标识'),
          ('voice.asr.confidence_threshold','0.75','decimal','voice','ASR 置信度阈值（本地模型不返回，保留）'),
          ('voice.semantic.confidence_threshold','0.60','decimal','voice','语义可信度确认阈值'),
          ('voice.dictionary.ttl_minutes','10','int','voice','业务词典缓存时间'),
          ('voice.tts.enabled','true','bool','voice','是否开启语音播报'),
          ('voice.tts.model','"edge-tts"','string','voice','语音合成服务标识'),
          ('voice.tts.voice','"zh-CN-XiaoxiaoNeural"','string','voice','Edge-TTS 发音人'),
          ('voice.tts.max_chars','500','int','voice','单次播报字符上限'),
          ('voice.transcript.retention_days','90','int','voice','转写文本保留天数'),
          ('report.schedule.hour','8','int','report','报告生成小时'),
          ('report.schedule.minute','0','int','report','报告生成分钟'),
          ('alert.scan.interval_minutes','60','int','alert','预警扫描间隔'),
          ('alert.cooldown_hours','24','int','alert','同一预警目标冷却时间'),
          ('alert.overstock.no_sales_days','90','int','alert','判定积压的无出库天数'),
          ('alert.price.change_window_days','30','int','alert','价格对比窗口'),
          ('alert.price.change_ratio','0.15','decimal','alert','价格异常涨跌幅阈值'),
          ('alert.receivable.overdue_days','30','int','alert','应收超期天数'),
          ('alert.payable.due_days','30','int','alert','应付到期天数'),
          ('alert.device_fault.repeat_count','3','int','alert','设备重复故障次数阈值'),
          ('alert.device_fault.period_days','7','int','alert','设备重复故障统计周期'),
          ('alert.profit.decline_months','2','int','alert','利润率连续下降月数'),
          ('alert.profit.decline_points','5','decimal','alert','利润率累计下降百分点')
        ON CONFLICT (config_key) DO NOTHING
        """
    )

    # 全部岗位可进入语音入口，业务权限不变
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'voice', 'create', 'company' FROM positions p
        ON CONFLICT (position_id, resource, action, data_scope) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope, business_domain)
        SELECT p.id, v.resource, v.action, v.data_scope, v.business_domain
        FROM positions p
        JOIN (VALUES
          ('general_manager','alert','update','company',NULL::text),
          ('general_manager','safe_stock','read','company',NULL::text),
          ('finance_head','alert','update','department',NULL::text),
          ('business_head','alert','read','department',NULL::text),
          ('business_head','alert','update','department',NULL::text),
          ('business_head','safe_stock','read','department',NULL::text),
          ('warehouse_head','alert','read','department',NULL::text),
          ('warehouse_head','alert','update','department',NULL::text),
          ('warehouse_head','safe_stock','read','business_domain','inventory'),
          ('warehouse_head','safe_stock','update','business_domain','inventory'),
          ('production_head','alert','read','department',NULL::text),
          ('production_head','alert','update','department',NULL::text),
          ('logistics_head','alert','read','department',NULL::text),
          ('logistics_head','alert','update','department',NULL::text),
          ('security_head','alert','read','department',NULL::text),
          ('security_head','alert','update','department',NULL::text)
        ) AS v(position_code, resource, action, data_scope, business_domain)
          ON p.code = v.position_code
        ON CONFLICT (position_id, resource, action, data_scope) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM position_permissions
        WHERE resource IN ('voice','safe_stock')
           OR (resource = 'alert' AND action = 'update')
           OR (resource = 'alert' AND action = 'read' AND data_scope = 'department')
        """
    )
    op.execute(
        "DELETE FROM system_configs WHERE config_key LIKE 'voice.%' "
        "OR config_key LIKE 'report.schedule.%' OR config_key LIKE 'alert.%'"
    )
