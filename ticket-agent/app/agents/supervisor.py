"""Supervisor 路由：按问题关键词选择知识库、运营、财务、业务单据或 V1 工单 Agent。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.agents import (
    business_agent,
    calculator,
    finance_agent,
    knowledge_agent,
    ops_agent,
    vehicle_agent,
)
from app.services.permission_service import Principal

WO_NO_RE = re.compile(r"WO\d{8,}")
CREATE_WORDS = ("创建", "新建", "开单", "起草", "生成草稿", "开一张", "做一张", "帮我开")

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "business": (
        "采购单",
        "销售单",
        "出入库单",
        "单据",
        "单号",
        "草稿",
        "待办",
        "待处理",
        "待审核",
        "待执行",
        "待入库",
        "未入库",
        "待出库",
        "未出库",
        "履约",
        "审核通过",
        "驳回",
        "冲销",
        "红冲",
        "退货",
        "预警",
        "盘点",
        "档案",
        "信用额度",
    ),
    "finance": (
        "收入",
        "成本",
        "利润",
        "毛利",
        "净利",
        "资金",
        "现金流",
        "应收",
        "应付",
        "余额",
        "费用",
        "盈利",
        "亏损",
        "盈亏",
        "生意",
        "营业额",
        "账龄",
        "收款",
        "付款",
        "资金流水",
    ),
    "operations": (
        "采购",
        "销售",
        "库存",
        "客户",
        "供应商",
        "结存",
        "周转",
        "订单",
        "出入库",
        "出库",
        "入库",
        "台账",
        "流水",
        "存煤",
        "存量",
        "库存金额",
        "煤价",
        "售价",
        "涨价",
        "降价",
    ),
    "knowledge": (
        "制度",
        "流程",
        "手册",
        "合同",
        "报价",
        "文档",
        "规定",
        "政策",
        "依据",
        "知识库",
    ),
    "work_order": (
        "工单",
        "报修",
        "报销单",
        "巡查",
        "运输异常",
        "派单",
        "分配",
        "提交处理",
    ),
    "calculator": (
        "计算",
        "算一下",
        "算算",
        "等于多少",
        "乘以",
        "除以",
        "加上",
        "减去",
    ),
    "vehicle": (
        "车辆",
        "用车",
        "查车",
        "派车",
        "车牌",
        "司机",
        "出车",
        "发运",
        "里程",
        "油耗",
        "车管",
        "车况",
        "保养",
        "年检",
        "几台车",
        "哪些车",
        "能派",
        "可派",
        "半挂",
        "牵引车",
        "挂车",
        "车队",
    ),
}


def has_domain_keyword(question: str) -> bool:
    return any(question.count(word) for words in DOMAIN_KEYWORDS.values() for word in words)


def route_domain(question: str) -> str:
    if WO_NO_RE.search(question):
        return "work_order"
    # 明确的建单动作优先归业务域，避免"创建出库单"被运营分析域接走
    if any(word in question for word in CREATE_WORDS) and any(
        word in question for word in ("出库", "入库", "采购单", "销售单", "单据", "草稿")
    ):
        return "business"
    # 车辆说法优先归车辆域：避免"用车费用"被财务域、"申请用车"被运营域接走
    if any(
        word in question
        for word in ("用车", "车辆", "查车", "派车", "车牌", "半挂", "牵引车", "挂车", "车队")
    ):
        return "vehicle"
    scores = {
        domain: sum(question.count(word) for word in words)
        for domain, words in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=lambda domain: scores[domain])
    if scores[best] == 0:
        return "work_order"
    # 平票时留在工单域：工单系统里"采购单""报销单"等说法优先按工单处理
    if scores["work_order"] and scores["work_order"] == scores[best]:
        return "work_order"
    return best


def run(
    db: Session,
    principal: Principal,
    question: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    top_k: int | None = None,
    domain: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    domain = domain or route_domain(question)
    if domain == "knowledge":
        result = knowledge_agent.run(db, principal, question, top_k=top_k)
    elif domain == "operations":
        result = ops_agent.run(db, principal, question, start_date=start_date, end_date=end_date)
    elif domain == "finance":
        result = finance_agent.run(
            db,
            principal,
            question,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
        )
    elif domain == "business":
        result = business_agent.run(
            db,
            principal,
            question,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
        )
    elif domain == "vehicle":
        result = vehicle_agent.run(
            db,
            principal,
            question,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
        )
    elif domain == "calculator":
        result = calculator.run(question)
    else:
        result = {
            "status": "ok",
            "answer": None,
            "sources": [],
            "missing": [],
            "delegate": "work_order_agent",
        }
    return {"domain": domain, **result}
