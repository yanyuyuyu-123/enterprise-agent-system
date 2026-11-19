"""Agent 对话编排：会话、确认执行与 Agent 日志。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents import llm, supervisor
from app.agents.graph import CONFIRM_WORDS, STATUS_LABELS, GraphDeps, get_graph
from app.core.errors import AppError
from app.core.logging import logger
from app.models.misc import AgentLog
from app.services import agent_history_service, confirm_service
from app.services.agent_context import (
    AgentContext,
    reset_agent_context,
    set_agent_context,
)
from app.services.flow_service import get_config_int
from app.services.permission_service import Principal
from app.tools.executor import execute_tool

AGENT_NAME = "work_order_agent"

DOMAIN_INTENTS = {
    "knowledge": "knowledge_query",
    "operations": "operations_query",
    "finance": "finance_query",
    "calculator": "calculator",
    "business": "business_query",
    "vehicle": "vehicle_query",
}

INTRO_TEXT = (
    "我是企业智能助手，可以帮你处理这些事：\n"
    "1. 工单：用自然语言创建报修、报销、安全巡查、运输异常工单，"
    "查询工单、查看详情、分配处理人、提交处理结果。\n"
    "2. 制度流程：查询企业知识库里的制度、流程、手册、合同、报价。\n"
    "3. 经营数据：采购、销售、库存、客户、供应商的汇总。\n"
    "4. 财务数据：收入、成本、利润、资金、应收应付的汇总，"
    "应收应付账龄、资金流水查询，登记收付款（先请你确认）。\n"
    "5. 业务单据：按单号查采购/销售/出入库单，查看待办和履约进度，"
    "创建草稿、提交、审核（写操作先请你确认）。\n"
    "6. 半挂车队：查半挂车状态和可派车辆，统计发运车次、吨位、里程与费用，"
    "写车队运输报告，提派车申请和审批（写操作先请你确认）。\n"
    "直接把问题发给我就行，涉及写操作会先请你确认。"
)

OFF_TOPIC_ANSWER = "与公司无关的内容不给予回答。"

CAPABILITY_HINTS = (
    "你是谁",
    "你叫什么",
    "你是什么",
    "你是干什么",
    "你能做什么",
    "你能干",
    "你会什么",
    "你能帮我",
    "怎么用",
    "使用说明",
    "自我介绍",
    "介绍一下你",
    "介绍下你",
    "介绍你自己",
    "你能介绍",
    "你好",
    "您好",
    "在吗",
)

SUCCESS_ACTIONS = {
    "create": "工单 {order_no} 已创建，当前状态：{status}。",
    "assign": "工单 {order_no} 已分配给处理人，当前状态：{status}。",
    "submit": "工单 {order_no} 的处理结果已提交，当前状态：{status}。",
    "review": "工单 {order_no} 审核完成，当前状态：{status}。",
}

# 业务单据状态（采购/销售/出入库/财务）与工单状态是两套枚举
DOC_STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "pending_execute": "待执行",
    "approved": "已审核",
    "rejected": "已驳回",
    "void": "已作废",
}


def _doc_status_label(status: Any) -> str:
    return DOC_STATUS_LABELS.get(str(status), STATUS_LABELS.get(str(status), str(status)))


def chat(
    db: Session,
    principal: Principal,
    *,
    message: str | None = None,
    session_id: str | None = None,
    confirm_token: str | None = None,
    cancel: bool = False,
) -> dict[str, Any]:
    sid = (session_id or "").strip() or uuid.uuid4().hex
    history = agent_history_service.recent_messages(db, principal, sid)

    if cancel:
        if not confirm_token:
            raise AppError(1001, "缺少确认令牌", 422)
        confirm_service.cancel(confirm_token, user_id=principal.user_id)
        data = _payload(sid, None, "已取消，未执行任何操作。")
    elif confirm_token:
        data = _execute_confirmation(db, principal, sid, confirm_token)
    else:
        text = (message or "").strip()
        if not text:
            raise AppError(1001, "消息不能为空", 422)

        if text in CONFIRM_WORDS:
            token = _pending_token(principal, sid)
            if token:
                data = _execute_confirmation(db, principal, sid, token)
            else:
                data = _run_graph(db, principal, sid, text, history)
        else:
            domain_answer = _run_other_domain(db, principal, sid, text, history)
            data = (
                domain_answer
                if domain_answer is not None
                else _run_graph(db, principal, sid, text, history)
            )

    _record_exchange(
        db,
        principal,
        data,
        message=message,
        cancel=cancel,
        confirm_token=confirm_token,
    )
    return data


def _record_exchange(
    db: Session,
    principal: Principal,
    data: dict[str, Any],
    *,
    message: str | None,
    cancel: bool,
    confirm_token: str | None,
) -> None:
    """把本轮问答写入会话历史，供“历史会话”恢复。"""
    sid = str(data.get("session_id") or "").strip()
    if not sid:
        return
    if message and message.strip():
        user_text = message.strip()
    elif cancel:
        user_text = "取消该操作"
    elif confirm_token:
        user_text = "确认执行"
    else:
        return

    answer = str(data.get("answer") or "").strip()
    if not answer and data.get("confirmation"):
        answer = "该操作需要确认后执行。"
    sources = data.get("sources") or (data.get("source") or {}).get("sources") or []
    agent_history_service.record_exchange(
        db,
        principal,
        session_id=sid,
        user_text=user_text,
        answer=answer,
        sources=sources,
        intent=str(data.get("intent")) if data.get("intent") else None,
    )


def _active_work_order_draft(principal: Principal, sid: str) -> bool:
    """工单流程未走完（等待补充信息或确认）时，后续消息仍交给工单 Agent。"""
    try:
        snapshot = get_graph().get_state(_thread_config(principal, sid))
    except Exception:  # noqa: BLE001
        return False
    values = snapshot.values or {}
    return bool(values.get("draft_slots")) or bool(values.get("confirmation"))


def _run_other_domain(
    db: Session,
    principal: Principal,
    sid: str,
    text: str,
    history: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Supervisor 路由：非工单问题直接交给知识库 / 运营 / 财务 Agent。"""
    if not supervisor.has_domain_keyword(text) and _is_capability(text):
        return _direct_answer(sid, INTRO_TEXT)

    if _active_work_order_draft(principal, sid):
        return None

    if supervisor.has_domain_keyword(text):
        domain = supervisor.route_domain(text)
        if domain == "work_order":
            return None
        return _answer_domain(db, principal, sid, domain, text, history)

    # 没有领域关键词：可能是追问，也可能是系统范围之外的问题
    scope = _screen_scope(text, history)
    if scope and scope["scope"] == "off_topic":
        return _direct_answer(sid, OFF_TOPIC_ANSWER)
    if scope and scope["scope"] == "capability":
        return _direct_answer(sid, INTRO_TEXT)
    if scope and scope["scope"] == "business":
        domain = scope["domain"]
        if domain == "work_order":
            return None
        return _answer_domain(db, principal, sid, domain, scope["question"] or text, history)

    # 模型不可用时退回按上一轮领域推断
    if not history:
        return None
    domain, question = _resolve_followup(text, history)
    if domain == "work_order":
        return None
    return _answer_domain(db, principal, sid, domain, question, history)


def _is_capability(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("hi", "hello", "hey"):
        return True
    return any(hint in lowered for hint in CAPABILITY_HINTS)


def _screen_scope(text: str, history: list[dict[str, str]]) -> dict[str, str] | None:
    """判断问题是否属于公司业务范围；模型不可用时返回 None 交给后续降级。"""
    try:
        data = llm.screen(text, history)
    except llm.LLMError:
        return None
    scope = str(data.get("scope") or "").strip()
    if scope not in ("capability", "off_topic", "business"):
        return None
    domain = str(data.get("domain") or "").strip()
    if domain != "work_order" and domain not in DOMAIN_INTENTS:
        domain = "work_order"
    return {
        "scope": scope,
        "domain": domain,
        "question": str(data.get("question") or "").strip(),
    }


def _direct_answer(sid: str, answer: str) -> dict[str, Any]:
    return {
        "session_id": sid,
        "intent": None,
        "answer": answer,
        "confirmation": None,
        "sources": [],
        "source": {},
        "tool_result": None,
    }


def _answer_domain(
    db: Session,
    principal: Principal,
    sid: str,
    domain: str,
    question: str,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        result = supervisor.run(db, principal, question, domain=domain, session_id=sid)
    except AppError as exc:
        # 无权限、参数不符等业务错误直接作为回答返回，不向前端抛 error 事件
        return {
            "session_id": sid,
            "intent": DOMAIN_INTENTS.get(domain, domain),
            "answer": exc.message,
            "confirmation": None,
            "sources": [],
            "source": {"domain": domain, "sources": []},
            "tool_result": None,
        }
    sources = result.get("sources") or []
    answer = str(result.get("answer") or "暂时没有可用的结果。")
    confirmation = result.get("confirmation")
    # 知识库检索结果是原始片段，交给模型提炼成简短回答；其余领域仅在追问时改写
    # 车辆报告本身已是成稿，不再二次改写，避免被压缩或改写数字
    if (history or (domain == "knowledge" and sources)) and domain != "vehicle":
        answer = _compose_followup_answer(question, history, result) or answer
    _write_domain_log(db, principal, sid, domain, question, result)
    return {
        "session_id": sid,
        "intent": DOMAIN_INTENTS.get(domain, domain),
        "answer": answer,
        "confirmation": confirmation,
        "sources": sources,
        "source": {"domain": domain, "sources": sources},
        "tool_result": None,
    }


def _resolve_followup(text: str, history: list[dict[str, str]]) -> tuple[str, str]:
    """把缺少关键词的追问改写成完整问题，并判断它属于哪个领域。"""
    rewritten = text
    try:
        rewritten = llm.rewrite(text, history)
    except llm.LLMError:
        rewritten = text
    if supervisor.has_domain_keyword(rewritten):
        return supervisor.route_domain(rewritten), rewritten
    return _previous_domain(history), rewritten


def _previous_domain(history: list[dict[str, str]]) -> str:
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        content = item.get("content") or ""
        if supervisor.has_domain_keyword(content):
            return supervisor.route_domain(content)
    return "work_order"


def _compose_followup_answer(
    question: str, history: list[dict[str, str]], result: dict[str, Any]
) -> str | None:
    """用历史对话 + 本次查询数据组织回答，避免追问时答非所问。"""
    context = str(result.get("answer") or "")
    titles = [
        str(source.get("title") or "")
        for source in result.get("sources") or []
        if source.get("title")
    ]
    if titles:
        context = f"{context}\n来源：{'、'.join(titles[:3])}"
    try:
        return llm.converse(question, history, context) or None
    except llm.LLMError:
        return None


def _write_domain_log(
    db: Session,
    principal: Principal,
    sid: str,
    domain: str,
    text: str,
    result: dict[str, Any],
) -> None:
    db.add(
        AgentLog(
            session_id=sid[:64],
            user_id=principal.user_id,
            agent_name=f"{domain}_agent"[:64],
            intent=DOMAIN_INTENTS.get(domain, domain)[:64],
            tool_name=domain[:64],
            input_summary=text[:500],
            output_summary=str(result.get("answer") or "")[:500],
            success=result.get("status") != "failed",
            error_code=None,
            latency_ms=0,
        )
    )
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("agent log write failed")
        db.rollback()


def _thread_config(principal: Principal, sid: str, deps: GraphDeps | None = None) -> dict:
    configurable: dict[str, Any] = {"thread_id": f"u{principal.user_id}:{sid}"}
    if deps is not None:
        configurable["deps"] = deps
    return {"configurable": configurable}


def _pending_token(principal: Principal, sid: str) -> str | None:
    try:
        snapshot = get_graph().get_state(_thread_config(principal, sid))
    except Exception:  # noqa: BLE001
        logger.exception("agent state load failed")
        snapshot = None
    card = ((snapshot.values or {}) if snapshot else {}).get("confirmation")
    if isinstance(card, dict):
        token = card.get("confirm_token")
        if token:
            return str(token)
    # 业务单据等非工单域不在 LangGraph 里，令牌按会话单独索引
    return confirm_service.pending_for_session(principal.user_id, sid)


def _run_graph(
    db: Session,
    principal: Principal,
    sid: str,
    text: str,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    timeout_s = float(get_config_int(db, "agent.tool.timeout_seconds", 5))
    deps = GraphDeps(db=db, principal=principal, session_id=sid, tool_timeout_s=timeout_s)
    token = set_agent_context(AgentContext(session_id=sid))
    try:
        state = get_graph().invoke(
            {"original_text": text, "session_id": sid, "history": history},
            _thread_config(principal, sid, deps),
        )
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent graph failed", extra={"session_id": sid})
        raise AppError(4000, "Agent 处理失败，请稍后重试或改用表单入口", 503) from exc
    finally:
        reset_agent_context(token)

    _write_logs(db, principal, sid, state)
    return {
        "session_id": sid,
        "intent": state.get("intent"),
        "answer": state.get("answer") or "",
        "confirmation": state.get("confirmation"),
        "source": state.get("source") or {},
        "tool_result": state.get("tool_result"),
    }


def _execute_confirmation(
    db: Session, principal: Principal, sid: str, token: str
) -> dict[str, Any]:
    data = confirm_service.consume(token, user_id=principal.user_id)
    action = str(data.get("action") or "")
    args = dict(data.get("params") or {})
    session_id = str(data.get("session_id") or sid)
    timeout_s = float(get_config_int(db, "agent.tool.timeout_seconds", 5))

    context_token = set_agent_context(AgentContext(session_id=session_id))
    try:
        result, meta = execute_tool(action, args, principal, timeout_s=timeout_s)
    finally:
        reset_agent_context(context_token)

    _write_one_log(
        db,
        principal,
        session_id,
        intent="confirmation",
        tool_name=action,
        args=args,
        result=result,
        meta=meta,
    )

    if result.get("ok"):
        data = result.get("data") or {}
        order_no = (
            data.get("order_no")
            or data.get("movement_no")
            or data.get("flow_no")
            or data.get("alert_no")
            or data.get("application_no")
            or args.get("work_order_id")
        )
        status = data.get("status")
        action_tail = action.split(".")[-1]
        business_templates = {
            "submit_order": "单据 {order_no} 已提交，当前状态：{status}。",
            "review_order": "单据 {order_no} 审核完成，当前状态：{status}。",
            "create_purchase_draft": "采购草稿 {order_no} 已创建。",
            "create_sales_draft": "销售草稿 {order_no} 已创建。",
            "create_movement_draft": "出入库草稿 {order_no} 已创建。",
        }
        finance_templates = {
            "create_cash_flow": "资金流水 {order_no} 已登记，当前状态：{status}。",
        }
        if action.startswith("business."):
            if action_tail == "submit_order":
                answer = (
                    f"单据 {order_no} 已提交并自动审核通过。"
                    if status == "approved"
                    else f"单据 {order_no} 已提交，当前状态：{_doc_status_label(status)}。"
                )
            else:
                template = business_templates.get(action_tail)
                answer = (
                    template.format(order_no=order_no, status=_doc_status_label(status))
                    if template
                    else "操作已完成。"
                )
        elif action.startswith("finance."):
            template = finance_templates.get(action_tail)
            answer = (
                template.format(order_no=order_no, status=_doc_status_label(status))
                if template
                else "操作已完成。"
            )
        elif action.startswith("wms."):
            answer = (
                f"预警 {order_no} 已认领。"
                if action_tail == "alert_acknowledge"
                else "操作已完成。"
            )
        elif action.startswith("vehicle."):
            if action_tail == "create_application":
                answer = f"派车申请 {order_no} 已提交，等待审批。"
            elif action_tail == "approve_application":
                if data.get("status") == "approved":
                    plate = data.get("plate_no")
                    answer = f"派车申请 {order_no} 已批准" + (
                        f"，已派车 {plate}。" if plate else "。"
                    )
                else:
                    answer = f"派车申请 {order_no} 已驳回。"
            else:
                answer = "操作已完成。"
        else:
            template = SUCCESS_ACTIONS.get(action_tail)
            answer = (
                template.format(order_no=order_no, status=STATUS_LABELS.get(status, status))
                if template
                else "操作已完成。"
            )
    else:
        answer = str(result.get("message") or "操作未执行，请稍后重试。")

    return {
        "session_id": session_id,
        "intent": "confirmation",
        "answer": answer,
        "confirmation": None,
        "source": result.get("source") or {},
        "tool_result": result,
    }


def _payload(sid: str, intent: str | None, answer: str) -> dict[str, Any]:
    return {
        "session_id": sid,
        "intent": intent,
        "answer": answer,
        "confirmation": None,
        "source": {},
        "tool_result": None,
    }


def _write_logs(db: Session, principal: Principal, sid: str, state: dict[str, Any]) -> None:
    intent = state.get("intent")
    answer = (state.get("answer") or "")[:200]
    for call in state.get("llm_calls") or []:
        is_tool = call.get("kind") == "tool"
        db.add(
            AgentLog(
                session_id=sid[:64],
                user_id=principal.user_id,
                agent_name=AGENT_NAME,
                intent=str(intent)[:64] if intent else None,
                tool_name=str(call.get("name") or "unknown")[:64],
                input_summary=("intent=" + str(intent))[:500] if not is_tool else None,
                output_summary=answer if is_tool else None,
                success=bool(call.get("success")),
                error_code=call.get("error_code"),
                latency_ms=int(call.get("latency_ms") or 0),
            )
        )
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("agent log write failed")
        db.rollback()


def _write_one_log(
    db: Session,
    principal: Principal,
    sid: str,
    *,
    intent: str,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    meta: dict[str, Any],
) -> None:
    summary = json.dumps(args, ensure_ascii=False, default=str)[:500]
    db.add(
        AgentLog(
            session_id=sid[:64],
            user_id=principal.user_id,
            agent_name=AGENT_NAME,
            intent=intent[:64],
            tool_name=tool_name[:64],
            input_summary=summary,
            output_summary=str(result.get("message") or "")[:200],
            success=bool(result.get("ok")),
            error_code=result.get("error_code"),
            latency_ms=int(meta.get("latency_ms") or 0),
        )
    )
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("agent log write failed")
        db.rollback()
