from __future__ import annotations

from app.tools.business_order_tools import (
    tool_cancel_order,
    tool_create_movement_draft,
    tool_create_purchase_draft,
    tool_create_sales_draft,
    tool_fulfillment_reminders,
    tool_movement_detail,
    tool_movement_list,
    tool_pending_tasks,
    tool_purchase_order_detail,
    tool_purchase_order_list,
    tool_receivable_payable,
    tool_review_order,
    tool_sales_order_detail,
    tool_sales_order_list,
    tool_stock_by_product,
    tool_submit_order,
    tool_update_order,
)
from app.tools.business_tools import (
    tool_customer_summary,
    tool_inventory_query,
    tool_purchase_summary,
    tool_sales_summary,
    tool_supplier_summary,
)
from app.tools.crm_wms_tools import (
    tool_alert_acknowledge,
    tool_alert_list,
    tool_check_list,
    tool_customer_profile,
    tool_supplier_profile,
)
from app.tools.finance_tools import (
    tool_cash_flow_list,
    tool_create_cash_flow,
    tool_metric_query,
    tool_receivable_payable_aging,
)
from app.tools.knowledge_tools import tool_search
from app.tools.specs import OUTPUT_SCHEMA, ToolSpec
from app.tools.vehicle_tools import (
    tool_approve_car_application,
    tool_car_application_list,
    tool_create_car_application,
    tool_vehicle_list,
    tool_vehicle_report_data,
    tool_vehicle_usage_stats,
)
from app.tools.work_order_tools import (
    tool_assign,
    tool_assign_candidates,
    tool_create,
    tool_detail,
    tool_query,
    tool_review,
    tool_submit,
    tool_summary,
)


def _input(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


TOOLS: dict[str, ToolSpec] = {
    "work_order.create": ToolSpec(
        name="work_order.create",
        description="创建工单；需要类别、标题，按类别补充明细字段",
        input_schema=_input(
            {
                "category": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string"},
                "device_id": {"type": "integer"},
                "fault_description": {"type": "string"},
                "expense_type": {"type": "string"},
                "amount": {"type": "number"},
                "patrol_area": {"type": "string"},
                "hazard_description": {"type": "string"},
                "trip_no": {"type": "string"},
                "exception_type": {"type": "string"},
            },
            ["category", "title"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "create"),
        is_write=True,
        handler=tool_create,
    ),
    "work_order.query": ToolSpec(
        name="work_order.query",
        description="按权限范围查询工单列表",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string"},
                "keyword": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_query,
    ),
    "work_order.detail": ToolSpec(
        name="work_order.detail",
        description="查看单张工单详情，含明细、流转记录、审核记录、附件",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_detail,
    ),
    "work_order.summary": ToolSpec(
        name="work_order.summary",
        description="总结工单处理过程，并统计重复故障次数",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_summary,
    ),
    "work_order.assign_candidates": ToolSpec(
        name="work_order.assign_candidates",
        description="列出该类别工单可分配的处理人",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_assign_candidates,
    ),
    "work_order.assign": ToolSpec(
        name="work_order.assign",
        description="把工单分配给处理人（写操作，需二次确认）",
        input_schema=_input(
            {
                "work_order_id": {"type": "integer"},
                "assignee_id": {"type": "integer"},
                "version": {"type": "integer"},
                "comment": {"type": "string"},
            },
            ["work_order_id", "assignee_id", "version"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order_assign", "assign"),
        is_write=True,
        handler=tool_assign,
    ),
    "work_order.submit": ToolSpec(
        name="work_order.submit",
        description="提交处理结果（写操作，需二次确认）",
        input_schema=_input(
            {
                "work_order_id": {"type": "integer"},
                "version": {"type": "integer"},
                "content": {"type": "string"},
                "result": {"type": "string"},
            },
            ["work_order_id", "version", "content"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "update"),
        is_write=True,
        handler=tool_submit,
    ),
    "work_order.review": ToolSpec(
        name="work_order.review",
        description="审核工单：通过或驳回（写操作，需二次确认）",
        input_schema=_input(
            {
                "work_order_id": {"type": "integer"},
                "version": {"type": "integer"},
                "decision": {"type": "string"},
                "comment": {"type": "string"},
            },
            ["work_order_id", "version", "decision"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order_review", "review"),
        is_write=True,
        handler=tool_review,
    ),
    "knowledge.search": ToolSpec(
        name="knowledge.search",
        description="在企业知识库中检索制度、流程、合同等文档，返回依据与位置",
        input_schema=_input({"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("knowledge_document", "read"),
        is_write=False,
        handler=tool_search,
    ),
    "business.purchase_summary": ToolSpec(
        name="business.purchase_summary",
        description="采购数量、金额与平均采购价（按订单日期）",
        input_schema=_input({"start_date": {"type": "string"}, "end_date": {"type": "string"}}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("purchase_order", "read"),
        is_write=False,
        handler=tool_purchase_summary,
    ),
    "business.sales_summary": ToolSpec(
        name="business.sales_summary",
        description="销售数量、金额、平均售价与客户贡献",
        input_schema=_input({"start_date": {"type": "string"}, "end_date": {"type": "string"}}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("sales_order", "read"),
        is_write=False,
        handler=tool_sales_summary,
    ),
    "business.inventory_query": ToolSpec(
        name="business.inventory_query",
        description="库存结存、出入库数量与周转率，可按仓库过滤",
        input_schema=_input(
            {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "warehouse_id": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "read"),
        is_write=False,
        handler=tool_inventory_query,
    ),
    "business.customer_summary": ToolSpec(
        name="business.customer_summary",
        description="客户总数、销售金额与客户贡献占比",
        input_schema=_input({"start_date": {"type": "string"}, "end_date": {"type": "string"}}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("customer", "read"),
        is_write=False,
        handler=tool_customer_summary,
    ),
    "business.supplier_summary": ToolSpec(
        name="business.supplier_summary",
        description="供应商总数与启用数量",
        input_schema=_input({}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("supplier", "read"),
        is_write=False,
        handler=tool_supplier_summary,
    ),
    "business.purchase_order_detail": ToolSpec(
        name="business.purchase_order_detail",
        description="按采购单号查看采购单详情、履约进度与剩余数量",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("purchase_order", "read"),
        is_write=False,
        handler=tool_purchase_order_detail,
    ),
    "business.sales_order_detail": ToolSpec(
        name="business.sales_order_detail",
        description="按销售单号查看销售单详情、履约进度与剩余数量",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("sales_order", "read"),
        is_write=False,
        handler=tool_sales_order_detail,
    ),
    "business.movement_detail": ToolSpec(
        name="business.movement_detail",
        description="按出入库单号查看单据详情、来源、冲销状态与明细",
        input_schema=_input({"order_no": {"type": "string"}}, ["order_no"]),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "read"),
        is_write=False,
        handler=tool_movement_detail,
    ),
    "business.stock_by_product": ToolSpec(
        name="business.stock_by_product",
        description="按产品关键字/仓库查询当前库存结存",
        input_schema=_input(
            {"keyword": {"type": "string"}, "warehouse_id": {"type": "integer"}}
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "read"),
        is_write=False,
        handler=tool_stock_by_product,
    ),
    "business.receivable_payable": ToolSpec(
        name="business.receivable_payable",
        description="查询应收、应付明细与合计",
        input_schema=_input(
            {
                "record_type": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("finance_record", "read"),
        is_write=False,
        handler=tool_receivable_payable,
    ),
    "business.pending_tasks": ToolSpec(
        name="business.pending_tasks",
        description="汇总当前用户可见的待执行、待审核单据",
        input_schema=_input({}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_pending_tasks,
    ),
    "business.purchase_order_list": ToolSpec(
        name="business.purchase_order_list",
        description="按状态、供应商、履约状态、日期查询采购单列表",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "keyword": {"type": "string"},
                "supplier_id": {"type": "integer"},
                "fulfillment_status": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("purchase_order", "read"),
        is_write=False,
        handler=tool_purchase_order_list,
    ),
    "business.sales_order_list": ToolSpec(
        name="business.sales_order_list",
        description="按状态、客户、履约状态、日期查询销售单列表",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "keyword": {"type": "string"},
                "customer_id": {"type": "integer"},
                "fulfillment_status": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("sales_order", "read"),
        is_write=False,
        handler=tool_sales_order_list,
    ),
    "business.movement_list": ToolSpec(
        name="business.movement_list",
        description="按状态、仓库、类型、来源、日期查询出入库单列表",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "warehouse_id": {"type": "integer"},
                "keyword": {"type": "string"},
                "movement_type": {"type": "string"},
                "source_type": {"type": "string"},
                "source_id": {"type": "integer"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "read"),
        is_write=False,
        handler=tool_movement_list,
    ),
    "business.fulfillment_reminders": ToolSpec(
        name="business.fulfillment_reminders",
        description="查询已审核但未完成入库/出库的采购单和销售单",
        input_schema=_input(
            {
                "order_type": {"type": "string"},
                "limit": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=False,
        handler=tool_fulfillment_reminders,
    ),
    "business.update_order": ToolSpec(
        name="business.update_order",
        description="修改草稿/被驳回采购或销售单的数量、单价、备注（写操作，需二次确认）",
        input_schema=_input(
            {
                "order_type": {"type": "string"},
                "order_id": {"type": "integer"},
                "version": {"type": "integer"},
                "remark": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                    },
                },
            },
            ["order_type", "order_id", "version"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=True,
        handler=tool_update_order,
    ),
    "business.cancel_order": ToolSpec(
        name="business.cancel_order",
        description="作废草稿/待审核/已审核采购或销售单（写操作，需二次确认）",
        input_schema=_input(
            {
                "order_type": {"type": "string"},
                "order_id": {"type": "integer"},
                "version": {"type": "integer"},
                "reason": {"type": "string"},
            },
            ["order_type", "order_id", "version"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=True,
        handler=tool_cancel_order,
    ),
    "business.create_purchase_draft": ToolSpec(
        name="business.create_purchase_draft",
        description="创建采购草稿（写操作，需二次确认）",
        input_schema=_input(
            {
                "supplier_id": {"type": "integer"},
                "order_date": {"type": "string"},
                "expected_date": {"type": "string"},
                "remark": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                    },
                },
            },
            ["supplier_id", "items"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("purchase_order", "create"),
        is_write=True,
        handler=tool_create_purchase_draft,
    ),
    "business.create_sales_draft": ToolSpec(
        name="business.create_sales_draft",
        description="创建销售草稿（写操作，需二次确认）",
        input_schema=_input(
            {
                "customer_id": {"type": "integer"},
                "order_date": {"type": "string"},
                "remark": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                    },
                },
            },
            ["customer_id", "items"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("sales_order", "create"),
        is_write=True,
        handler=tool_create_sales_draft,
    ),
    "business.create_movement_draft": ToolSpec(
        name="business.create_movement_draft",
        description="创建出入库草稿；可由已审核订单按剩余数量生成（写操作，需二次确认）",
        input_schema=_input(
            {
                "movement_type": {"type": "string"},
                "warehouse_id": {"type": "integer"},
                "source_type": {"type": "string"},
                "source_id": {"type": "integer"},
                "remark": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "number"},
                        },
                    },
                },
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "create"),
        is_write=True,
        handler=tool_create_movement_draft,
    ),
    "business.submit_order": ToolSpec(
        name="business.submit_order",
        description="提交采购/销售/出入库单据（写操作，需二次确认）",
        input_schema=_input(
            {
                "order_type": {"type": "string"},
                "order_id": {"type": "integer"},
                "version": {"type": "integer"},
            },
            ["order_type", "order_id", "version"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=True,
        handler=tool_submit_order,
    ),
    "business.review_order": ToolSpec(
        name="business.review_order",
        description="审核采购/销售/出入库单据（写操作，需二次确认）",
        input_schema=_input(
            {
                "order_type": {"type": "string"},
                "order_id": {"type": "integer"},
                "version": {"type": "integer"},
                "decision": {"type": "string"},
                "comment": {"type": "string"},
            },
            ["order_type", "order_id", "version", "decision"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("work_order", "read"),
        is_write=True,
        handler=tool_review_order,
    ),
    "finance.aging": ToolSpec(
        name="finance.aging",
        description="按往来单位查询应收应付账龄（0-30/31-60/61-90/90+ 天）",
        input_schema=_input(
            {
                "record_type": {"type": "string"},
                "as_of": {"type": "string"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("finance_record", "read"),
        is_write=False,
        handler=tool_receivable_payable_aging,
    ),
    "finance.cash_flow_list": ToolSpec(
        name="finance.cash_flow_list",
        description="按方向、状态、日期查询资金流水",
        input_schema=_input(
            {
                "direction": {"type": "string"},
                "status": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("finance_record", "read"),
        is_write=False,
        handler=tool_cash_flow_list,
    ),
    "finance.create_cash_flow": ToolSpec(
        name="finance.create_cash_flow",
        description="登记一笔收款或付款资金流水（写操作，需二次确认）",
        input_schema=_input(
            {
                "direction": {"type": "string"},
                "amount": {"type": "number"},
                "flow_date": {"type": "string"},
                "payment_method": {"type": "string"},
                "related_order_type": {"type": "string"},
                "related_order_id": {"type": "integer"},
                "remark": {"type": "string"},
            },
            ["direction", "amount"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("finance_record", "create"),
        is_write=True,
        handler=tool_create_cash_flow,
    ),
    "crm.customer_profile": ToolSpec(
        name="crm.customer_profile",
        description="查询客户档案，含累计应收、信用额度与可用额度",
        input_schema=_input(
            {"keyword": {"type": "string"}, "customer_id": {"type": "integer"}}
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("customer", "read"),
        is_write=False,
        handler=tool_customer_profile,
    ),
    "crm.supplier_profile": ToolSpec(
        name="crm.supplier_profile",
        description="查询供应商档案，含累计应付",
        input_schema=_input(
            {"keyword": {"type": "string"}, "supplier_id": {"type": "integer"}}
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("supplier", "read"),
        is_write=False,
        handler=tool_supplier_profile,
    ),
    "wms.alert_list": ToolSpec(
        name="wms.alert_list",
        description="查询库存、价格、应收应付等预警",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "alert_type": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("alert", "read"),
        is_write=False,
        handler=tool_alert_list,
    ),
    "wms.alert_acknowledge": ToolSpec(
        name="wms.alert_acknowledge",
        description="认领待处理预警（写操作，需二次确认）",
        input_schema=_input({"alert_id": {"type": "integer"}, "alert_no": {"type": "string"}}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("alert", "update"),
        is_write=True,
        handler=tool_alert_acknowledge,
    ),
    "wms.check_list": ToolSpec(
        name="wms.check_list",
        description="按状态查询盘点单列表",
        input_schema=_input(
            {
                "status": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("inventory", "read"),
        is_write=False,
        handler=tool_check_list,
    ),
    "vehicle.list": ToolSpec(
        name="vehicle.list",
        description="查询半挂车档案：车牌、挂车号、车型、载重、司机、可派状态",
        input_schema=_input(
            {
                "keyword": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["available", "in_use", "maintenance", "disabled"],
                },
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("vehicle", "read"),
        is_write=False,
        handler=tool_vehicle_list,
    ),
    "vehicle.usage_stats": ToolSpec(
        name="vehicle.usage_stats",
        description="按车辆、项目、部门或月份统计发运车次、里程、吨位与费用",
        input_schema=_input(
            {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "group_by": {
                    "type": "string",
                    "enum": ["car", "project", "dept", "month"],
                },
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("car_application", "read"),
        is_write=False,
        handler=tool_vehicle_usage_stats,
    ),
    "vehicle.report_data": ToolSpec(
        name="vehicle.report_data",
        description="获取车队运输报告所需的全量统计数据",
        input_schema=_input({"start_date": {"type": "string"}, "end_date": {"type": "string"}}),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("car_application", "read"),
        is_write=False,
        handler=tool_vehicle_report_data,
    ),
    "vehicle.application_list": ToolSpec(
        name="vehicle.application_list",
        description="查询派车申请列表，可按单号、状态、日期筛选",
        input_schema=_input(
            {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected", "cancelled", "completed"],
                },
                "keyword": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("car_application", "read"),
        is_write=False,
        handler=tool_car_application_list,
    ),
    "vehicle.create_application": ToolSpec(
        name="vehicle.create_application",
        description="提交半挂车派车申请（写操作，需二次确认）",
        input_schema=_input(
            {
                "start_address": {"type": "string"},
                "end_address": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "cargo": {"type": "string"},
                "tonnage": {"type": "number"},
                "project": {"type": "string"},
                "reason": {"type": "string"},
                "remark": {"type": "string"},
            },
            ["start_address", "end_address", "start_time"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("car_application", "create"),
        is_write=True,
        handler=tool_create_car_application,
    ),
    "vehicle.approve_application": ToolSpec(
        name="vehicle.approve_application",
        description="审批派车申请，可同时指定派车车辆（写操作，需二次确认）",
        input_schema=_input(
            {
                "application_no": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
                "comment": {"type": "string"},
                "plate_no": {"type": "string"},
            },
            ["application_no", "decision"],
        ),
        output_schema=OUTPUT_SCHEMA,
        required_permission=("car_application", "approve"),
        is_write=True,
        handler=tool_approve_car_application,
    ),
}

WRITE_TOOLS = frozenset(name for name, spec in TOOLS.items() if spec.is_write)


def get_tool(name: str) -> ToolSpec | None:
    return TOOLS.get(name)


def list_tool_names() -> list[str]:
    return sorted(TOOLS)
