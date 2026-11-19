"""规则降级：模型不可用或超时时保证流程可用，同时用于本地测试。

只做关键词级判断，宁可返回 unknown 交给用户澄清，也不猜。
"""

from __future__ import annotations

import re
from typing import Any

ORDER_NO_RE = re.compile(r"WO\d{8,}")
DEVICE_NO_RE = re.compile(r"(DEV-?\d+)", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d+(?:\.\d{1,2})?)\s*(?:元|块)?")

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "device_repair": ("维修", "报修", "故障", "坏了", "设备"),
    "expense_reimbursement": ("报销", "费用", "差旅", "发票", "采购", "购物", "垫付"),
    "security_patrol": ("巡查", "巡检", "隐患", "安全"),
    "transport_exception": ("运输", "物流", "车次", "运单", "配送"),
}

STATUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "supplementing": ("补充信息", "待补充"),
    "pending_assignment": ("待分配",),
    "pending_process": ("待处理",),
    "processing": ("处理中",),
    "pending_review": ("待审核",),
    "rejected": ("已驳回", "被驳回"),
    "completed": ("已完成", "完成"),
    "cancelled": ("已取消", "取消"),
}

UNSUPPORTED_KEYWORDS = (
    "库存",
    "采购",
    "销售",
    "利润",
    "财务",
    "合同",
    "报价",
    "制度",
    "知识库",
    "维修手册",
)


def detect_intent(text: str) -> str:
    # "创建采购工单"这类请求里的“采购/库存”是工单内容，不是要查经营数据
    creating = any(word in text for word in ("创建", "新建", "申请", "上报", "报修", "提交工单"))
    if any(word in text for word in UNSUPPORTED_KEYWORDS) and not creating:
        return "unsupported"
    if any(word in text for word in ("总结", "复盘", "发生了什么")):
        return "work_order_summary"
    if ORDER_NO_RE.search(text) and any(
        word in text for word in ("审核", "审批", "通过", "驳回")
    ):
        return "work_order_review"
    if any(word in text for word in ("分配", "指派", "派给", "安排给", "安排人")):
        return "work_order_assign"
    if any(word in text for word in ("提交", "处理完了", "已修好", "已处理", "结果如下")):
        return "work_order_submit"
    if any(word in text for word in ("进度", "详情", "进展", "流转记录", "到哪一步")):
        return "work_order_detail"
    if any(word in text for word in ("查询", "查一下", "看一下", "有哪些", "列表", "哪些工单")):
        return "work_order_query"
    if any(word in text for word in ("创建", "新建", "报修", "报销", "上报", "申请", "提交工单")):
        return "work_order_create"
    if ORDER_NO_RE.search(text):
        return "work_order_detail"
    if "工单" in text:
        return "work_order_query"
    return "unknown"


def detect_category(text: str) -> str | None:
    for code, words in CATEGORY_KEYWORDS.items():
        if any(word in text for word in words):
            return code
    return None


def detect_status(text: str) -> str | None:
    for code, words in STATUS_KEYWORDS.items():
        if any(word in text for word in words):
            return code
    return None


def detect_assignee(text: str) -> str | None:
    match = re.search(r"(?:分配给|指派给|派给|交给)\s*([\u4e00-\u9fa5]{2,4})", text)
    return match.group(1) if match else None


def extract(intent: str, text: str) -> dict[str, Any]:
    """规则版实体提取，字段名与 Prompt 输出保持一致。"""
    entities: dict[str, Any] = {}
    order_no = ORDER_NO_RE.search(text)
    if order_no:
        entities["order_no"] = order_no.group(0)

    if intent == "work_order_create":
        category = detect_category(text)
        if category:
            entities["category"] = category
        entities["title"] = text.strip()[:30]
        entities["description"] = text.strip()
        device_no = DEVICE_NO_RE.search(text)
        if device_no:
            entities["device_no"] = device_no.group(1)
        if category == "expense_reimbursement":
            amount = AMOUNT_RE.search(text)
            if amount:
                entities["amount"] = amount.group(1)
            for code, words in {
                "travel": ("差旅", "出差"),
                "transport": ("交通", "打车"),
                "office": ("办公",),
                "entertainment": ("招待",),
                "purchase": ("采购", "购物"),
            }.items():
                if any(word in text for word in words):
                    entities["expense_type"] = code
                    break
        if category == "security_patrol":
            entities["patrol_area"] = text.strip()[:40]
            entities["hazard_description"] = text.strip()
        if category == "transport_exception":
            entities["exception_type"] = "other"
            entities["trip_no"] = entities.get("device_no") or text.strip()[:20]
    elif intent == "work_order_query":
        status = detect_status(text)
        if status:
            entities["status"] = status
        category = detect_category(text)
        if category:
            entities["category"] = category
        entities["keyword"] = order_no.group(0) if order_no else None
        entities["keyword"] = entities["keyword"] or None
    elif intent == "work_order_assign":
        assignee = detect_assignee(text)
        if assignee:
            entities["assignee_name"] = assignee
    elif intent == "work_order_submit":
        clean = ORDER_NO_RE.sub("", text)
        clean = re.sub(r"^(提交|处理结果|结果)[：:，,]?", "", clean.strip())
        entities["content"] = clean.strip() or text.strip()
        entities["result"] = entities["content"]
    elif intent == "work_order_review":
        if "驳回" in text:
            entities["decision"] = "reject"
            comment = ORDER_NO_RE.sub("", text.split("驳回", 1)[1])
            comment = re.sub(r"^(?:原因|意见)?[：:，,。\s]+", "", comment.strip())
            if comment:
                entities["comment"] = comment.strip()
        elif any(word in text for word in ("通过", "同意")):
            entities["decision"] = "approve"
    elif intent == "work_order_summary":
        pass

    return {key: value for key, value in entities.items() if value not in (None, "")}
