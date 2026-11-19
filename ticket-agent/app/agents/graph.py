"""V1 工单 Agent 编排：rewrite → classify → extract → select_tool → confirm/execute → respond。

节点只做语言理解与路由；所有业务写操作走 `app/tools` → `app/services`，权限、
数据范围、状态机与 HTTP 接口完全一致。V1 不启用 Supervisor。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents import llm, rules
from app.agents.checkpointer import get_checkpointer
from app.agents.state import AgentState
from app.core.constants import (
    ALL_CATEGORIES,
    CATEGORY_ASSIGNEE_POSITIONS,
    CATEGORY_DEVICE_REPAIR,
    CATEGORY_EXPENSE_REIMBURSEMENT,
    CATEGORY_SECURITY_PATROL,
    CATEGORY_TRANSPORT_EXCEPTION,
)
from app.core.errors import AppError
from app.services import confirm_service
from app.services.flow_service import user_has_position
from app.services.permission_service import Principal
from app.services.work_order_service import visible_order, visible_order_by_no
from app.tools import work_order_tools as wt
from app.tools.executor import execute_tool
from app.tools.registry import WRITE_TOOLS

PROMPT_BY_INTENT: dict[str, str] = {
    "work_order_create": "work_order_create.v1.md",
    "work_order_query": "work_order_query.v1.md",
    "work_order_detail": "work_order_query.v1.md",
    "work_order_summary": "work_order_summary.v1.md",
    "work_order_assign": "work_order_assign.v1.md",
    "work_order_submit": "work_order_submit.v1.md",
    "work_order_review": "work_order_review.v1.md",
}

SUPPORTED_INTENTS = frozenset(PROMPT_BY_INTENT)

CATEGORY_LABELS: dict[str, str] = {
    "device_repair": "设备维修",
    "expense_reimbursement": "报销",
    "security_patrol": "安全巡查",
    "transport_exception": "运输异常",
}

EXPENSE_TYPE_LABELS: dict[str, str] = {
    "travel": "差旅费",
    "transport": "交通费",
    "office": "办公费",
    "entertainment": "招待费",
    "purchase": "采购杂费",
    "other": "其他",
}

CREATE_CATEGORY_GUIDE = (
    "我还不确定你要创建哪一类工单，目前支持这四类：\n"
    "1. 设备维修：说清哪台设备、出现什么故障\n"
    "2. 报销：说明报销类型和金额，例如“采购杂费 1000 元”\n"
    "3. 安全巡查：说明巡查区域和发现的隐患\n"
    "4. 运输异常：提供运输单号和异常情况\n"
    "也可以直接这样说：帮我创建一个采购报销工单，金额 1000 元。"
)

STATUS_LABELS: dict[str, str] = {
    "supplementing": "补充信息",
    "pending_assignment": "待分配",
    "pending_process": "待处理",
    "processing": "处理中",
    "pending_review": "待审核",
    "rejected": "已驳回",
    "completed": "已完成",
    "cancelled": "已取消",
}

PRIORITY_LABELS: dict[str, str] = {
    "low": "低",
    "normal": "普通",
    "high": "高",
    "urgent": "紧急",
}

CONFIRM_WORDS = frozenset({"确认", "确定", "好的", "好", "执行", "提交", "同意"})


@dataclass(slots=True)
class GraphDeps:
    db: Session
    principal: Principal
    session_id: str
    tool_timeout_s: float = 5.0


def _deps(config: RunnableConfig) -> GraphDeps:
    return config["configurable"]["deps"]


def _calls(state: AgentState) -> list[dict[str, Any]]:
    return list(state.get("llm_calls") or [])


def _call_meta(name: str, started: float, ok: bool, error_code: str | None = None) -> dict:
    return {
        "kind": "llm",
        "name": name,
        "success": ok,
        "error_code": error_code,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def node_rewrite(state: AgentState) -> dict[str, Any]:
    text = (state.get("original_text") or "").strip()
    calls: list[dict[str, Any]] = []
    rewritten = text
    if text:
        started = time.perf_counter()
        try:
            rewritten = llm.rewrite(text, state.get("history"))
            calls.append(_call_meta("rewrite", started, True))
        except llm.LLMError as exc:
            calls.append(_call_meta("rewrite", started, False, "4001" if exc.timeout else "4000"))
    # 新一轮对话清空上一轮的瞬时字段，保留 history 与 draft_slots
    return {
        "rewritten_text": rewritten,
        "llm_calls": calls,
        "intent": "unknown",
        "entities": {},
        "tool_name": None,
        "tool_args": {},
        "tool_result": None,
        "confirmation": None,
        "needs_clarification": False,
        "clarification": None,
        "answer": "",
        "source": {},
        "error": None,
    }


def node_classify(state: AgentState) -> dict[str, Any]:
    text = state.get("rewritten_text") or state.get("original_text") or ""
    calls = _calls(state)
    started = time.perf_counter()
    try:
        data = llm.classify(text, state.get("history"))
        intent = str(data.get("intent") or "unknown")
        calls.append(_call_meta("classify", started, True))
    except llm.LLMError as exc:
        intent = rules.detect_intent(text)
        calls.append(_call_meta("classify", started, False, "4001" if exc.timeout else "4000"))

    if intent not in SUPPORTED_INTENTS and intent not in ("unsupported", "unknown"):
        intent = "unknown"
    return {"intent": intent, "llm_calls": calls}


def node_extract(state: AgentState) -> dict[str, Any]:
    intent = state.get("intent") or "unknown"
    prompt = PROMPT_BY_INTENT.get(intent)
    if prompt is None:
        return {"entities": {}}

    text = state.get("rewritten_text") or state.get("original_text") or ""
    calls = _calls(state)
    started = time.perf_counter()
    try:
        entities = llm.extract(prompt, text, state.get("history"))
        calls.append(_call_meta(f"extract:{intent}", started, True))
    except llm.LLMError as exc:
        entities = rules.extract(intent, text)
        calls.append(
            _call_meta(f"extract:{intent}", started, False, "4001" if exc.timeout else "4000")
        )
    return {"entities": entities, "llm_calls": calls}


def _can(principal: Principal, resource: str, action: str) -> bool:
    return any(p.resource == resource and p.action == action for p in principal.permissions)


def _clarify(message: str, *, intent: str, slots: dict[str, Any]) -> dict[str, Any]:
    return {
        "needs_clarification": True,
        "clarification": message,
        "tool_name": None,
        "tool_args": {},
        "confirmation": None,
        "draft_intent": intent,
        "draft_slots": slots,
    }


def _answer_directly(message: str) -> dict[str, Any]:
    return {
        "needs_clarification": False,
        "clarification": None,
        "tool_name": None,
        "tool_args": {},
        "confirmation": None,
        "draft_intent": None,
        "draft_slots": {},
        "answer": message,
    }


def _created_args(slots: dict[str, Any]) -> dict[str, Any]:
    category = slots["category"]
    args: dict[str, Any] = {
        "category": category,
        "title": slots["title"],
        "description": slots.get("description"),
        "priority": slots.get("priority") or "normal",
    }
    if category == CATEGORY_DEVICE_REPAIR:
        args["device_id"] = slots["device_id"]
        args["fault_description"] = slots.get("fault_description") or slots.get("description")
    elif category == CATEGORY_EXPENSE_REIMBURSEMENT:
        args["expense_type"] = slots.get("expense_type")
        args["amount"] = slots.get("amount")
    elif category == CATEGORY_SECURITY_PATROL:
        args["patrol_area"] = slots.get("patrol_area")
        args["hazard_description"] = slots.get("hazard_description")
    elif category == CATEGORY_TRANSPORT_EXCEPTION:
        args["trip_no"] = slots.get("trip_no")
        args["exception_type"] = slots.get("exception_type")
    return args


def _missing_create_fields(db: Session, slots: dict[str, Any]) -> list[str]:
    category = slots["category"]
    missing: list[str] = []
    if not slots.get("title"):
        missing.append("标题")

    if category == CATEGORY_DEVICE_REPAIR:
        if not slots.get("device_id"):
            device = wt.find_device(
                db,
                device_no=slots.get("device_no"),
                device_name=slots.get("device_name"),
            )
            if device is not None:
                slots["device_id"] = device.id
            else:
                missing.append("设备编号（未找到对应设备）")
        if not (slots.get("fault_description") or slots.get("description")):
            missing.append("故障描述")
    elif category == CATEGORY_EXPENSE_REIMBURSEMENT:
        if not slots.get("expense_type"):
            missing.append("费用类型")
        amount = wt.parse_amount(slots.get("amount"))
        if amount is None:
            missing.append("金额")
        else:
            slots["amount"] = str(amount)
    elif category == CATEGORY_SECURITY_PATROL:
        if not slots.get("patrol_area"):
            missing.append("巡查区域")
    elif category == CATEGORY_TRANSPORT_EXCEPTION:
        if not slots.get("trip_no"):
            missing.append("运输单号")
        if not slots.get("exception_type"):
            slots["exception_type"] = "other"
    return missing


def node_select_tool(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    deps = _deps(config)
    db = deps.db
    intent = state.get("intent") or "unknown"

    if intent == "unsupported":
        return _answer_directly(
            "当前版本暂不支持该能力，敬请期待。目前可以用自然语言创建、查询、查看、"
            "分配和提交工单。"
        )
    if intent == "unknown":
        return _clarify(
            "没太理解你的意思，可以换个说法，或直接用表单入口提交工单。",
            intent=intent,
            slots={},
        )

    draft_intent = state.get("draft_intent")
    slots: dict[str, Any] = dict(state.get("draft_slots") or {}) if draft_intent == intent else {}
    slots.update({k: v for k, v in (state.get("entities") or {}).items() if v not in (None, "")})
    slots = {key: value for key, value in slots.items() if value not in (None, "")}

    if intent == "work_order_create":
        if not _can(deps.principal, "work_order", "create"):
            return _answer_directly("你当前没有创建工单的权限。")
        if slots.get("category") not in ALL_CATEGORIES:
            return _clarify(CREATE_CATEGORY_GUIDE, intent=intent, slots=slots)
        missing = _missing_create_fields(db, slots)
        if missing:
            label = CATEGORY_LABELS.get(slots["category"], "")
            prefix = f"已按{label}工单处理" if label else "创建工单"
            hint = ""
            if slots["category"] == CATEGORY_EXPENSE_REIMBURSEMENT:
                expense_type = slots.get("expense_type")
                if expense_type in EXPENSE_TYPE_LABELS:
                    hint = f"报销类型：{EXPENSE_TYPE_LABELS[expense_type]}。"
                else:
                    options = "、".join(EXPENSE_TYPE_LABELS.values())
                    hint = f"报销类型可选：{options}。"
            return _clarify(
                f"{prefix}，还缺少：{'、'.join(missing)}。{hint}请补充。",
                intent=intent,
                slots=slots,
            )
        return {
            "tool_name": "work_order.create",
            "tool_args": _created_args(slots),
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": intent,
            "draft_slots": slots,
        }

    if intent == "work_order_query":
        page = int(slots.get("page") or 1)
        page_size = min(int(slots.get("page_size") or 10), 20)
        status = slots.get("status")
        category = slots.get("category")
        return {
            "tool_name": "work_order.query",
            "tool_args": {
                "status": status if status in STATUS_LABELS else None,
                "category": category if category in ALL_CATEGORIES else None,
                "priority": slots.get("priority"),
                "keyword": slots.get("keyword"),
                "page": page,
                "page_size": page_size,
            },
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": None,
            "draft_slots": {},
        }

    order_no = str(slots.get("order_no") or "").strip()
    if not order_no:
        return _clarify("请提供工单号，例如 WO202611100001。", intent=intent, slots=slots)

    try:
        order = visible_order_by_no(db, deps.principal, order_no)
    except AppError:
        return _answer_directly("工单不存在，或你无权查看该工单。")

    if intent in ("work_order_detail", "work_order_summary"):
        tool = "work_order.detail" if intent == "work_order_detail" else "work_order.summary"
        return {
            "tool_name": tool,
            "tool_args": {"order_no": order.order_no},
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": None,
            "draft_slots": {},
        }

    if intent == "work_order_submit":
        if not _can(deps.principal, "work_order", "update"):
            return _answer_directly("你当前没有提交处理结果的权限。")
        content = str(slots.get("content") or "").strip()
        if not content:
            return _clarify(
                f"请补充 {order.order_no} 的处理结果，我会整理后提交。",
                intent=intent,
                slots=slots,
            )
        return {
            "tool_name": "work_order.submit",
            "tool_args": {
                "work_order_id": order.id,
                "version": order.version,
                "content": content,
                "result": slots.get("result") or content,
            },
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": None,
            "draft_slots": {},
        }

    if intent == "work_order_review":
        if not _can(deps.principal, "work_order_review", "review"):
            return _answer_directly("你当前没有审核工单的权限。")
        decision = str(slots.get("decision") or "").strip()
        if decision not in ("approve", "reject"):
            return _clarify(
                f"请说明 {order.order_no} 是审核通过还是驳回。",
                intent=intent,
                slots=slots,
            )
        comment = str(slots.get("comment") or "").strip()
        if decision == "reject" and not comment:
            return _clarify(
                f"驳回 {order.order_no} 需要填写意见，请补充。",
                intent=intent,
                slots=slots,
            )
        if order.status != "pending_review":
            label = STATUS_LABELS.get(order.status, order.status)
            return _answer_directly(f"{order.order_no} 当前状态为{label}，不能审核。")
        return {
            "tool_name": "work_order.review",
            "tool_args": {
                "work_order_id": order.id,
                "version": order.version,
                "decision": decision,
                "comment": comment or None,
            },
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": None,
            "draft_slots": {},
        }

    # work_order_assign
    if not _can(deps.principal, "work_order_assign", "assign"):
        return _answer_directly("你当前没有分配工单的权限。")
    assignee_name = str(slots.get("assignee_name") or "").strip()
    assignee_no = str(slots.get("assignee_employee_no") or "").strip()
    if not assignee_name and not assignee_no:
        return {
            "tool_name": "work_order.assign_candidates",
            "tool_args": {"order_no": order.order_no},
            "needs_clarification": False,
            "clarification": None,
            "confirmation": None,
            "draft_intent": None,
            "draft_slots": {},
        }

    users = wt.find_active_users(db, name=assignee_name or None, employee_no=assignee_no or None)
    if not users and assignee_name:
        users = wt.search_users_by_name(db, assignee_name)
    if len(users) != 1:
        hint = "没有找到该人员" if not users else "匹配到多人，请用工号指定"
        candidates = wt.assign_candidates(db, order)
        names = "、".join(f"{item['name']}({item['employee_no']})" for item in candidates) or "无"
        return _answer_directly(f"{hint}。{order.order_no} 当前可分配人员：{names}。")

    assignee = users[0]
    codes = CATEGORY_ASSIGNEE_POSITIONS.get(order.category)
    if codes and not user_has_position(db, assignee.id, codes):
        return _answer_directly(
            f"{assignee.name} 的岗位与 {CATEGORY_LABELS.get(order.category, order.category)} "
            "工单不匹配，请选择对应岗位人员。"
        )
    return {
        "tool_name": "work_order.assign",
        "tool_args": {
            "work_order_id": order.id,
            "assignee_id": assignee.id,
            "version": order.version,
            "comment": None,
        },
        "needs_clarification": False,
        "clarification": None,
        "confirmation": None,
        "draft_intent": None,
        "draft_slots": {},
    }


def node_confirm(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    deps = _deps(config)
    tool_name = str(state.get("tool_name"))
    args = dict(state.get("tool_args") or {})

    order_no = None
    if args.get("work_order_id"):
        try:
            order = visible_order(deps.db, deps.principal, int(args["work_order_id"]))
            order_no = order.order_no
        except AppError:
            order_no = None

    if tool_name == "work_order.create":
        label = CATEGORY_LABELS.get(str(args.get("category")), "工单")
        summary = f"创建{label}工单《{args.get('title')}》"
    elif tool_name == "work_order.assign":
        name = "指定人员"
        if args.get("assignee_id"):
            assignee = wt.find_user_by_id(deps.db, int(args["assignee_id"]))
            name = assignee.name if assignee is not None else name
        summary = f"将工单 {order_no or args.get('work_order_id')} 分配给 {name}"
    elif tool_name == "work_order.submit":
        summary = f"提交工单 {order_no or args.get('work_order_id')} 的处理结果"
    else:
        summary = f"执行 {tool_name}"

    card = confirm_service.issue(
        deps.db,
        deps.principal,
        action=tool_name,
        params=args,
        summary=summary,
        session_id=deps.session_id,
        work_order_id=args.get("work_order_id"),
        version=args.get("version"),
    )
    return {
        "confirmation": card,
        "answer": f"{summary}。确认后执行，确认有效期 5 分钟。",
        "needs_clarification": False,
        "draft_intent": None,
        "draft_slots": {},
    }


def node_execute(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    deps = _deps(config)
    tool_name = str(state.get("tool_name"))
    result, meta = execute_tool(
        tool_name,
        dict(state.get("tool_args") or {}),
        deps.principal,
        timeout_s=deps.tool_timeout_s,
    )
    calls = _calls(state) + [meta]
    return {
        "tool_result": result,
        "source": result.get("source") or {},
        "llm_calls": calls,
        "confirmation": None,
    }


def _fmt_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _render_order_row(item: dict[str, Any]) -> str:
    return (
        f"{item['order_no']} {item['title']} | "
        f"{CATEGORY_LABELS.get(item['category'], item['category'])} | "
        f"{STATUS_LABELS.get(item['status'], item['status'])} | "
        f"{PRIORITY_LABELS.get(item['priority'], item['priority'])} | "
        f"期限 {_fmt_time(item.get('due_at'))}" + ("（已超时）" if item.get("is_overdue") else "")
    )


def _compose_answer(state: AgentState) -> str:
    if state.get("answer"):
        return str(state["answer"])
    if state.get("needs_clarification") and state.get("clarification"):
        return str(state["clarification"])
    result = state.get("tool_result") or {}
    tool_name = state.get("tool_name")
    data = result.get("data")

    if result.get("ok") is False:
        return str(result.get("message") or "操作失败，请稍后重试。")

    if tool_name == "work_order.query":
        items = (data or {}).get("items") or []
        total = (data or {}).get("total") or 0
        if not items:
            return "未查询到符合条件的工单。"
        lines = [f"共 {total} 条，当前显示 {len(items)} 条："]
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {_render_order_row(item)}")
        return "\n".join(lines)

    if tool_name == "work_order.assign_candidates":
        candidates = (data or {}).get("candidates") or []
        if not candidates:
            return f"{data.get('order_no')} 所属类别无需分配处理人。"
        lines = [f"{data.get('order_no')} 可分配人员："]
        for index, item in enumerate(candidates, start=1):
            lines.append(
                f"{index}. {item['name']}（{item['employee_no']}，{item['position_name']}）"
            )
        return "\n".join(lines)

    if tool_name in ("work_order.detail", "work_order.summary") and isinstance(data, dict):
        lines = [
            f"工单 {data['order_no']}《{data['title']}》",
            f"类别：{CATEGORY_LABELS.get(data['category'], data['category'])}；"
            f"状态：{STATUS_LABELS.get(data['status'], data['status'])}；"
            f"优先级：{PRIORITY_LABELS.get(data['priority'], data['priority'])}",
            f"创建人：{data.get('creator_id')}；处理人：{data.get('assignee_id') or '未分配'}；"
            f"审核人：{data.get('reviewer_id') or '未指定'}",
            f"分配时间：{_fmt_time(data.get('assigned_at'))}；"
            f"处理期限：{_fmt_time(data.get('due_at'))}；"
            f"完成时间：{_fmt_time(data.get('completed_at'))}",
        ]
        if data.get("is_overdue"):
            lines.append("该工单已超时。")
        records = data.get("records") or []
        if records:
            lines.append("最近流转：")
            for row in records[-5:]:
                lines.append(
                    f"- {_fmt_time(row.get('created_at'))} "
                    f"{row.get('operator_name')} {row.get('action')}"
                    + (f"：{row.get('comment')}" if row.get("comment") else "")
                )
        if tool_name == "work_order.summary":
            lines.append(
                f"审核轮次：{len(data.get('approvals') or [])} 次；"
                f"近 {data.get('repeat_period_days')} 天同类重复工单："
                f"{data.get('repeat_count')} 条。"
            )
            if data.get("repeat_count", 0) >= 2:
                lines.append("提示：该设备近期重复报修，建议安排专项排查。")
        return "\n".join(lines)

    if result.get("message"):
        return str(result["message"])
    return "已处理。"


def node_respond(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    answer = _compose_answer(state)
    history = list(state.get("history") or [])
    history.append({"role": "user", "content": state.get("original_text") or ""})
    history.append({"role": "assistant", "content": answer})
    history = history[-llm.HISTORY_LIMIT :]
    return {"answer": answer, "history": history}


def _route(state: AgentState) -> str:
    if state.get("needs_clarification") or not state.get("tool_name"):
        return "respond"
    if state.get("answer") and not state.get("tool_result"):
        return "respond"
    if state.get("tool_name") in WRITE_TOOLS:
        return "confirm"
    return "execute"


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("rewrite", node_rewrite)
    builder.add_node("classify", node_classify)
    builder.add_node("extract", node_extract)
    builder.add_node("select_tool", node_select_tool)
    builder.add_node("confirm", node_confirm)
    builder.add_node("execute", node_execute)
    builder.add_node("respond", node_respond)

    builder.set_entry_point("rewrite")
    builder.add_edge("rewrite", "classify")
    builder.add_edge("classify", "extract")
    builder.add_edge("extract", "select_tool")
    builder.add_conditional_edges(
        "select_tool",
        _route,
        {"confirm": "confirm", "execute": "execute", "respond": "respond"},
    )
    builder.add_edge("confirm", "respond")
    builder.add_edge("execute", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=get_checkpointer())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
