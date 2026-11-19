"""财务 Agent：汇总指标、应收应付账龄、资金流水查询与收付款登记。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.business import CashFlow, FinanceRecord
from app.services import confirm_service, metric_service
from app.services.permission_service import Principal, require_permission
from app.tools.executor import execute_tool

SHANGHAI = ZoneInfo("Asia/Shanghai")

AGING_WORDS = ("账龄", "欠款", "欠了多少", "没收回", "未收回", "还没付", "未付")
FLOW_WORDS = ("现金流", "资金流水", "流水明细", "收支明细", "收付款明细", "资金进出")
REGISTER_WORDS = ("登记", "记一笔", "记录一笔", "录入")
STATUS_LABELS = {"pending_review": "待审核", "approved": "已审核", "rejected": "已驳回", "void": "已作废"}
AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万元|万|元|块)?")


def _period(
    db: Session, start_date: date | None, end_date: date | None
) -> tuple[date, date, str]:
    end = end_date or datetime.now(SHANGHAI).date()
    start = start_date or end.replace(day=1)
    if start_date or end_date:
        return start, end, ""
    latest = db.scalar(select(func.max(FinanceRecord.record_date)))
    if latest and latest < start:
        return (
            latest.replace(day=1),
            latest,
            f"本月暂无财务数据，已按最近有数据的 {latest:%Y-%m} 统计。",
        )
    return start, end, ""


def _has_mock(db: Session, start: date, end: date) -> bool:
    record = db.scalar(
        select(func.count())
        .select_from(FinanceRecord)
        .where(
            FinanceRecord.is_mock.is_(True),
            FinanceRecord.record_date >= start,
            FinanceRecord.record_date <= end,
        )
    )
    flow = db.scalar(
        select(func.count())
        .select_from(CashFlow)
        .where(
            CashFlow.is_mock.is_(True),
            CashFlow.flow_date >= start,
            CashFlow.flow_date <= end,
        )
    )
    return bool(record or flow)


def _reply(
    answer: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    confirmation: dict[str, Any] | None = None,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "answer": answer,
        "sources": sources or [],
        "missing": missing or [],
        "confirmation": confirmation,
    }


def _date_range(text: str) -> tuple[date | None, date | None]:
    today = datetime.now(SHANGHAI).date()
    if "今天" in text:
        return today, today
    if "本月" in text or "这个月" in text:
        return today.replace(day=1), today
    if "上月" in text or "上个月" in text:
        last_month_end = today.replace(day=1) - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if "今年" in text:
        return today.replace(month=1, day=1), today
    return None, None


def _handle_aging(principal: Principal, text: str) -> dict[str, Any]:
    record_type = None
    if "应收" in text and "应付" not in text:
        record_type = "receivable"
    elif "应付" in text and "应收" not in text:
        record_type = "payable"
    args: dict[str, Any] = {}
    if record_type:
        args["record_type"] = record_type
    result, _meta = execute_tool("finance.aging", args, principal, timeout_s=10)
    if not result.get("ok"):
        return _reply(str(result.get("message") or "查询账龄失败。"))
    data = result["data"]
    lines = [f"截至 {data['as_of']}，按单据日期计算的账龄："]
    for key, label in (("receivable", "应收"), ("payable", "应付")):
        buckets = data[key]
        total = sum(Decimal(buckets[name]) for name in ("0-30", "31-60", "61-90", "90+"))
        lines.append(
            f"{label}合计 {total.quantize(Decimal('0.01'))}："
            f"0-30 天 {buckets['0-30']}，31-60 天 {buckets['31-60']}，"
            f"61-90 天 {buckets['61-90']}，90 天以上 {buckets['90+']}"
        )
    items = data.get("items") or []
    if items:
        lines.append("往来单位前 8 位：")
        for item in items[:8]:
            kind = "应收" if item["record_type"] == "receivable" else "应付"
            lines.append(
                f"- {item['counterparty_name'] or item['counterparty_type']}："
                f"{kind} {item['total']}（90 天以上 {item['90+']}）"
            )
    return _reply("\n".join(lines), sources=[{"type": "finance", "name": "aging"}])


def _handle_cash_flow(principal: Principal, text: str) -> dict[str, Any]:
    args: dict[str, Any] = {"page_size": 20}
    start, end = _date_range(text)
    if start is not None:
        args["start_date"] = start.isoformat()
        args["end_date"] = end.isoformat() if end else None
    if "收款" in text or "流入" in text or "收入" in text:
        args["direction"] = "in"
    elif "付款" in text or "流出" in text or "支出" in text:
        args["direction"] = "out"
    result, _meta = execute_tool("finance.cash_flow_list", args, principal, timeout_s=10)
    if not result.get("ok"):
        return _reply(str(result.get("message") or "查询资金流水失败。"))
    data = result["data"]
    items = data.get("items") or []
    if not items:
        return _reply("没有查到符合条件的资金流水。")
    inflow = sum(
        (Decimal(row["amount"]) for row in items if row["direction"] == "in"),
        Decimal("0"),
    )
    outflow = sum(
        (Decimal(row["amount"]) for row in items if row["direction"] == "out"),
        Decimal("0"),
    )
    lines = [
        f"共 {data['total']} 笔，当前显示 {len(items)} 笔，"
        f"流入 {inflow.quantize(Decimal('0.01'))}，流出 {outflow.quantize(Decimal('0.01'))}。"
    ]
    for row in items[:10]:
        status = STATUS_LABELS.get(row["status"], row["status"])
        direction = "收" if row["direction"] == "in" else "付"
        lines.append(
            f"- {row['flow_date']} {row['flow_no']}：{direction} {row['amount']}"
            f"（{row.get('payment_method') or '-'}，{status}）"
        )
    return _reply("\n".join(lines), sources=[{"type": "finance", "name": "cash_flow"}])


def _parse_amount(text: str) -> str | None:
    for match in AMOUNT_RE.finditer(text):
        value = match.group(1)
        unit = match.group(2) or ""
        if unit in ("万元", "万"):
            return str(Decimal(value) * 10000)
        return value
    return None


def _handle_register(
    db: Session, principal: Principal, text: str, session_id: str | None
) -> dict[str, Any]:
    amount = _parse_amount(text)
    if amount is None:
        return _reply("请说明金额，例如：登记收款 5000 元，银行转账。")
    if "付款" in text or "支出" in text or "付了" in text:
        direction = "out"
    elif "收款" in text or "进账" in text or "收到" in text:
        direction = "in"
    else:
        return _reply("请说明是收款还是付款，例如：登记收款 5000 元。")
    method = next(
        (item for item in ("现金", "银行", "转账", "微信", "支付宝") if item in text), None
    )
    if not session_id:
        return _reply("请重新发起会话后再登记。")
    label = "收款" if direction == "in" else "付款"
    summary = f"登记{label} {amount} 元" + (f"（{method}）" if method else "")
    card = confirm_service.issue(
        db,
        principal,
        action="finance.create_cash_flow",
        params={
            "direction": direction,
            "amount": amount,
            "payment_method": method,
            "remark": "用户通过智能助手登记",
        },
        summary=summary,
        session_id=session_id,
    )
    return _reply(f"将{summary}，确认执行吗？", confirmation=card)


def run(
    db: Session,
    principal: Principal,
    question: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    text = question.strip()
    try:
        if any(word in text for word in AGING_WORDS):
            return _handle_aging(principal, text)
        if any(word in text for word in REGISTER_WORDS) and any(
            word in text for word in ("收款", "付款", "进账", "支出")
        ):
            return _handle_register(db, principal, text, session_id)
        if any(word in text for word in FLOW_WORDS):
            return _handle_cash_flow(principal, text)
    except AppError as exc:
        return _reply(exc.message, missing=["财务数据（无权限或不可用）"])

    start, end, period_note = _period(db, start_date, end_date)
    try:
        require_permission(principal, "finance_record", "read")
        data = metric_service.finance_summary(db, start, end)
    except AppError as exc:
        return {
            "status": "failed",
            "answer": exc.message,
            "sources": [],
            "missing": ["财务指标（无权限或不可用）"],
        }

    lines = [
        f"收入 {data['revenue']}，成本 {data['cost']}，费用 {data['expense']}",
        f"毛利 {data['gross_profit']}（毛利率 {data['gross_margin'] or '—'}%），"
        f"净利 {data['net_profit']}",
        f"应收 {data['receivable']}，应付 {data['payable']}，"
        f"资金余额 {data['cash_balance']}（期间净流入 {data['net_cash_flow']}）",
    ]
    prefix = "【模拟数据】" if _has_mock(db, start, end) else ""
    if period_note:
        lines.insert(0, period_note)
    return {
        "status": "ok",
        "answer": prefix + "\n".join(lines),
        "sources": [
            {
                "type": "metric",
                "id": "finance_summary",
                "title": "财务汇总",
                "locator": f"{start.isoformat()}~{end.isoformat()}",
            }
        ],
        "missing": [],
        "confirmation": None,
    }
