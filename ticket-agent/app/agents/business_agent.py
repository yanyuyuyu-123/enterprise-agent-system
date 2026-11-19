"""业务单据 Agent：查单据/待办/库存/应收应付，以及带二次确认的写操作。"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents import llm
from app.core.errors import AppError
from app.models.business import Customer, Product, Supplier
from app.services import confirm_service, inventory_service
from app.services.permission_service import Principal
from app.tools.executor import execute_tool

ORDER_NO_RE = re.compile(r"\b(PO|SO|SM)\d{6,}\b", re.IGNORECASE)

STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审核",
    "pending_execute": "待执行",
    "approved": "已审核",
    "rejected": "已驳回",
    "void": "已作废",
}
FULFILLMENT_LABELS = {"none": "未执行", "partial": "部分执行", "completed": "已完成"}
TYPE_LABELS = {"purchase": "采购单", "sales": "销售单", "movement": "出入库单"}
PENDING_WORDS = ("待办", "待处理", "待审核", "待执行", "我的任务")
CREATE_WORDS = ("新建", "创建", "开单", "生成草稿", "起草")
REMINDER_WORDS = ("未入库", "待入库", "没入库", "未出库", "待出库", "没出库", "履约")
LIST_WORDS = ("采购单列表", "销售单列表", "最近的采购单", "最近的销售单", "本月采购", "本月销售")
ALERT_NO_RE = re.compile(r"AL\d{8,}", re.IGNORECASE)


def _tool(name: str, args: dict[str, Any], principal: Principal) -> tuple[bool, Any, str]:
    result, _meta = execute_tool(name, args, principal, timeout_s=10)
    return bool(result.get("ok")), result.get("data"), str(result.get("message") or "")


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


def _order_type(order_no: str) -> str:
    return {"PO": "purchase", "SO": "sales", "SM": "movement"}[order_no[:2].upper()]


def _find_order(
    db: Session, principal: Principal, order_no: str
) -> tuple[str, dict[str, Any]] | None:
    order_type = _order_type(order_no)
    if order_type == "purchase":
        from app.services import purchase_service

        data = purchase_service.list_purchase_orders(
            db, principal, keyword=order_no, page=1, page_size=5
        )
    elif order_type == "sales":
        from app.services import sales_service

        data = sales_service.list_sales_orders(
            db, principal, keyword=order_no, page=1, page_size=5
        )
    else:
        data = inventory_service.list_movements(
            db, principal, keyword=order_no, page=1, page_size=5
        )
    if order_type == "movement":
        return (
            order_type,
            next(
                (item for item in data["items"] if item.get("movement_no") == order_no),
                None,
            ),
        )
    return (
        order_type,
        next((item for item in data["items"] if item.get("order_no") == order_no), None),
    )


def _order_answer(order_type: str, data: dict[str, Any]) -> str:
    no = data.get("order_no") or data.get("movement_no")
    status = STATUS_LABELS.get(data.get("status"), data.get("status"))
    lines = [f"{TYPE_LABELS[order_type]} {no}：{status}，金额 {data.get('total_amount', '-')}。"]
    if order_type != "movement":
        fulfillment = FULFILLMENT_LABELS.get(
            data.get("fulfillment_status"), data.get("fulfillment_status")
        )
        lines.append(f"履约状态：{fulfillment}。")
        for item in data.get("items") or []:
            lines.append(
                f"- {item.get('product_name') or item.get('product_id')}："
                f"数量 {item['quantity']}，已执行 {item.get('executed_quantity', '0')}，"
                f"剩余 {item.get('remaining_quantity', '-')}"
            )
    else:
        lines.append(
            f"来源：{data.get('source_type')}"
            f"{' / ' + str(data.get('source_id')) if data.get('source_id') else ''}，"
            f"冲销状态：{'已冲销' if data.get('is_reversed') else '红字单' if data.get('reversal_of_id') else '正常'}。"
        )
        for item in data.get("items") or []:
            lines.append(
                f"- {item.get('product_name') or item.get('product_id')}：数量 {item['quantity']}"
            )
    return "\n".join(lines)


def _resolve_warehouse(
    db: Session, principal: Principal, text: str
) -> tuple[int | None, list[dict[str, Any]]]:
    rows = inventory_service.list_warehouses(db, principal)
    for row in rows:
        if row["name"] and row["name"] in text:
            return row["id"], rows
    if len(rows) == 1:
        return rows[0]["id"], rows
    return None, rows


def _date_range(text: str) -> tuple[date | None, date | None]:
    today = date.today()
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


def _handle_reminders(principal: Principal, text: str) -> dict[str, Any]:
    if "入" in text and "出" not in text:
        order_type = "purchase"
    elif "出" in text and "入" not in text:
        order_type = "sales"
    else:
        order_type = "all"
    ok, data, message = _tool(
        "business.fulfillment_reminders", {"order_type": order_type}, principal
    )
    if not ok:
        return _reply(message or "查询履约情况失败。")
    items = data.get("items") or []
    if not items:
        return _reply("当前没有未完成的采购或销售订单，履约都已完成。")
    lines = [f"有 {data['total']} 张订单还没执行完："]
    for item in items[:10]:
        kind = "采购单" if item["order_type"] == "purchase" else "销售单"
        status = FULFILLMENT_LABELS.get(item["fulfillment_status"], item["fulfillment_status"])
        remaining = "，".join(
            f"{line.get('product_name') or line['product_id']} 剩 {line['remaining_quantity']}"
            for line in item["lines"]
        )
        lines.append(f"- {kind} {item['order_no']}（{item['counterparty'] or '-'}）：{status}；{remaining}")
    return _reply("\n".join(lines), sources=[{"type": "business", "name": "fulfillment"}])


def _handle_list(principal: Principal, text: str) -> dict[str, Any]:
    is_purchase = "采购" in text
    tool_name = "business.purchase_order_list" if is_purchase else "business.sales_order_list"
    start, end = _date_range(text)
    args: dict[str, Any] = {"page_size": 10}
    if start is not None:
        args["start_date"] = start.isoformat()
        args["end_date"] = end.isoformat() if end else None
    if "待审核" in text:
        args["status"] = "pending_review"
    elif "草稿" in text:
        args["status"] = "draft"
    elif "已审核" in text or "已通过" in text:
        args["status"] = "approved"
    ok, data, message = _tool(tool_name, args, principal)
    if not ok:
        return _reply(message or "查询单据失败。")
    items = data.get("items") or []
    label = "采购单" if is_purchase else "销售单"
    if not items:
        return _reply(f"没有查到符合条件的{label}。")
    lines = [f"共 {data['total']} 张{label}，显示最近 {len(items)} 张："]
    for item in items:
        status = STATUS_LABELS.get(item["status"], item["status"])
        fulfillment = FULFILLMENT_LABELS.get(item["fulfillment_status"], "")
        counterparty = item.get("supplier_name") or item.get("customer_name") or "-"
        lines.append(
            f"- {item['order_no']}（{counterparty}）：{status}，"
            f"{fulfillment}，金额 {item['total_amount']}"
        )
    return _reply("\n".join(lines), sources=[{"type": "business", "name": "order_list"}])


def _handle_alerts(
    db: Session, principal: Principal, text: str, session_id: str | None
) -> dict[str, Any]:
    match = ALERT_NO_RE.search(text.upper())
    if match and any(word in text for word in ("认领", "处理", "接收")):
        alert_no = match.group(0)
        return _confirm(
            db,
            principal,
            session_id,
            action="wms.alert_acknowledge",
            params={"alert_no": alert_no},
            summary=f"认领预警 {alert_no}",
            prompt=f"将认领预警 {alert_no}，确认执行吗？",
        )
    args: dict[str, Any] = {"page_size": 10}
    if "已认领" in text:
        args["status"] = "acknowledged"
    elif "已关闭" in text:
        args["status"] = "closed"
    elif "全部" not in text:
        args["status"] = "open"
    ok, data, message = _tool("wms.alert_list", args, principal)
    if not ok:
        return _reply(message or "查询预警失败。")
    items = data.get("items") or []
    if not items:
        return _reply("没有查到符合条件的预警。")
    lines = [f"共 {data['total']} 条预警，显示最近 {len(items)} 条："]
    for item in items:
        day = (item.get("triggered_at") or "")[:10]
        lines.append(
            f"- {item['alert_no']}【{item['level']}】{item['title']}（{day}，{item['status']}）"
        )
    return _reply("\n".join(lines), sources=[{"type": "business", "name": "alerts"}])


PROFILE_STOP_WORDS = (
    "查一下",
    "查询",
    "查查",
    "看看",
    "看一下",
    "帮我",
    "档案",
    "资料",
    "资料卡",
    "信用额度",
    "信用",
    "欠款",
    "应收",
    "应付",
    "情况",
    "客户",
    "供应商",
    "查",
    "请",
    "的",
)


def _handle_profile(principal: Principal, text: str) -> dict[str, Any]:
    is_customer = "客户" in text
    keyword = text
    for word in PROFILE_STOP_WORDS:
        keyword = keyword.replace(word, " ")
    keyword = keyword.strip(" ，。？?、：:")
    if not keyword:
        return _reply(f"请说明{'客户' if is_customer else '供应商'}名称，例如：查客户 华北能源 的档案。")
    tool_name = "crm.customer_profile" if is_customer else "crm.supplier_profile"
    ok, data, message = _tool(tool_name, {"keyword": keyword}, principal)
    if not ok:
        return _reply(message or "查询档案失败。")
    lines = [f"{'客户' if is_customer else '供应商'} {data['name']}（{data['code']}）"]
    if data.get("contact_name") or data.get("phone"):
        lines.append(f"联系人：{data.get('contact_name') or '-'}，电话：{data.get('phone') or '-'}")
    lines.append(f"状态：{'启用' if data.get('status') == 'active' else '停用'}")
    if is_customer:
        lines.append(f"累计应收：{data['receivable_total']}")
        lines.append(
            f"信用额度：{data.get('credit_limit') or '0.00'}，可用额度：{data['credit_available']}"
        )
        if data.get("credit_exceeded"):
            lines.append("提示：当前应收已超过信用额度。")
    else:
        lines.append(f"累计应付：{data['payable_total']}")
    return _reply("\n".join(lines), sources=[{"type": "business", "name": "profile"}])


def _handle_checks(principal: Principal, text: str) -> dict[str, Any]:
    args: dict[str, Any] = {"page_size": 10}
    if "待审核" in text:
        args["status"] = "pending_review"
    elif "草稿" in text:
        args["status"] = "draft"
    elif "已审核" in text:
        args["status"] = "approved"
    ok, data, message = _tool("wms.check_list", args, principal)
    if not ok:
        return _reply(message or "查询盘点单失败。")
    items = data.get("items") or []
    if not items:
        return _reply("没有查到符合条件的盘点单。")
    lines = [f"共 {data['total']} 张盘点单，显示最近 {len(items)} 张："]
    for item in items:
        diff_lines = sum(
            1
            for line in item.get("items") or []
            if float(line.get("diff_quantity") or 0) != 0
        )
        lines.append(
            f"- {item['check_no']}（{item.get('check_date') or '-'}）："
            f"{STATUS_LABELS.get(item['status'], item['status'])}，差异 {diff_lines} 项"
        )
    return _reply("\n".join(lines), sources=[{"type": "business", "name": "checks"}])


def _confirm(
    db: Session,
    principal: Principal,
    session_id: str | None,
    *,
    action: str,
    params: dict[str, Any],
    summary: str,
    prompt: str,
) -> dict[str, Any]:
    if not session_id:
        return _reply(
            f"识别到写操作：{summary}。请到对应页面操作，或重新发起会话后再确认。"
        )
    card = confirm_service.issue(
        db,
        principal,
        action=action,
        params=params,
        summary=summary,
        session_id=session_id,
    )
    return _reply(prompt, confirmation=card)


def _handle_update(
    db: Session,
    principal: Principal,
    text: str,
    order_type: str,
    data: dict[str, Any],
    session_id: str | None,
) -> dict[str, Any]:
    quantity = re.search(r"数量[^0-9]{0,6}(\d+(?:\.\d+)?)", text)
    unit_price = re.search(r"单价[^0-9]{0,6}(\d+(?:\.\d+)?)", text)
    if not quantity and not unit_price:
        return _reply("请说明要把数量或单价改成多少，例如：把采购单 PO000001 数量改成 5。")

    items = data.get("items") or []
    if not items:
        return _reply("这张单没有明细可以修改。")
    matched = [
        item
        for item in items
        if item.get("product_name") and item["product_name"] in text
    ]
    targets = matched or items
    if len(targets) > 1:
        names = "、".join(item.get("product_name") or str(item["product_id"]) for item in items)
        return _reply(f"这张单有多条明细（{names}），请说明要改哪个产品。")

    target_id = targets[0]["product_id"]
    new_items = []
    for item in items:
        line_quantity = item["quantity"]
        line_price = item["unit_price"]
        if item["product_id"] == target_id:
            if quantity:
                line_quantity = quantity.group(1)
            if unit_price:
                line_price = unit_price.group(1)
        new_items.append(
            {
                "product_id": item["product_id"],
                "quantity": line_quantity,
                "unit_price": line_price,
            }
        )

    changes = []
    if quantity:
        changes.append(f"数量改为 {quantity.group(1)}")
    if unit_price:
        changes.append(f"单价改为 {unit_price.group(1)}")
    no = data.get("order_no")
    return _confirm(
        db,
        principal,
        session_id,
        action="business.update_order",
        params={
            "order_type": order_type,
            "order_id": data["id"],
            "version": data["version"],
            "items": new_items,
        },
        summary=f"修改{TYPE_LABELS[order_type]} {no}：{'，'.join(changes)}",
        prompt=f"将修改{TYPE_LABELS[order_type]} {no}（{'，'.join(changes)}），确认执行吗？",
    )


def _handle_order(
    db: Session,
    principal: Principal,
    text: str,
    order_no: str,
    session_id: str | None,
) -> dict[str, Any]:
    found = _find_order(db, principal, order_no)
    if not found or found[1] is None:
        return _reply(f"没有找到单据 {order_no}，请确认单号或权限范围。")
    order_type, data = found

    if any(word in text for word in ("冲销", "红冲")):
        return _reply(
            f"{TYPE_LABELS[order_type]} {order_no} 的冲销需要填写原因，"
            "请到对应单据页面点击“冲销”完成。"
        )

    if order_type == "movement":
        return _reply(_order_answer(order_type, data))

    if any(word in text for word in ("作废", "取消")):
        return _confirm(
            db,
            principal,
            session_id,
            action="business.cancel_order",
            params={
                "order_type": order_type,
                "order_id": data["id"],
                "version": data["version"],
                "reason": "用户通过智能助手取消",
            },
            summary=f"作废{TYPE_LABELS[order_type]} {order_no}",
            prompt=f"将作废{TYPE_LABELS[order_type]} {order_no}，确认执行吗？",
        )

    if ("数量" in text or "单价" in text) and any(
        word in text for word in ("改", "调", "修改")
    ):
        return _handle_update(db, principal, text, order_type, data, session_id)

    if any(word in text for word in ("生成入库单", "入库", "收货")) and order_type == "purchase":
        warehouse_id, warehouses = _resolve_warehouse(db, principal, text)
        if warehouse_id is None:
            names = "、".join(row["name"] for row in warehouses) or "无可用仓库"
            return _reply(f"请说明入库仓库（可选：{names}）。")
        return _confirm(
            db,
            principal,
            session_id,
            action="business.create_movement_draft",
            params={
                "movement_type": "inbound",
                "source_type": "purchase_order",
                "source_id": data["id"],
                "warehouse_id": warehouse_id,
            },
            summary=f"按采购单 {order_no} 剩余数量生成入库草稿",
            prompt=f"将按采购单 {order_no} 的剩余数量生成入库草稿，确认执行吗？",
        )

    if any(word in text for word in ("生成出库单", "出库", "发货")) and order_type == "sales":
        warehouse_id, warehouses = _resolve_warehouse(db, principal, text)
        if warehouse_id is None:
            names = "、".join(row["name"] for row in warehouses) or "无可用仓库"
            return _reply(f"请说明出库仓库（可选：{names}）。")
        return _confirm(
            db,
            principal,
            session_id,
            action="business.create_movement_draft",
            params={
                "movement_type": "outbound",
                "source_type": "sales_order",
                "source_id": data["id"],
                "warehouse_id": warehouse_id,
            },
            summary=f"按销售单 {order_no} 剩余数量生成出库草稿",
            prompt=f"将按销售单 {order_no} 的剩余数量生成出库草稿，确认执行吗？",
        )

    if "提交" in text and "审核" not in text:
        params = {
            "order_type": order_type,
            "order_id": data["id"],
            "version": data["version"],
        }
        return _confirm(
            db,
            principal,
            session_id,
            action="business.submit_order",
            params=params,
            summary=f"提交{TYPE_LABELS[order_type]} {order_no}",
            prompt=f"将提交{TYPE_LABELS[order_type]} {order_no}，确认执行吗？",
        )

    if "审核" in text or "通过" in text or "驳回" in text:
        decision = "reject" if "驳回" in text else "approve"
        comment = None
        if decision == "reject":
            return _reply("驳回需要填写原因，请到单据页面审核并填写意见。")
        params = {
            "order_type": order_type,
            "order_id": data["id"],
            "version": data["version"],
            "decision": decision,
        }
        return _confirm(
            db,
            principal,
            session_id,
            action="business.review_order",
            params=params,
            summary=f"审核通过{TYPE_LABELS[order_type]} {order_no}",
            prompt=f"将审核通过{TYPE_LABELS[order_type]} {order_no}，确认执行吗？",
        )

    return _reply(_order_answer(order_type, data))


def _match_partner(db: Session, model, value: str) -> list[Any]:
    keyword = f"%{value.strip()}%"
    return list(
        db.scalars(
            select(model)
            .where(
                model.deleted_at.is_(None),
                or_(model.name.ilike(keyword), model.code.ilike(keyword)),
            )
            .limit(5)
        ).all()
    )


PARTNER_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "公司", "集团")


def _similar_partners(db: Session, model, value: str) -> list[Any]:
    """全名匹配不到时，逐步缩短名称前缀做近似匹配，用于提示用户正确名称。"""
    key = value.strip()
    for suffix in PARTNER_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
            break
    for length in range(len(key), 1, -1):
        rows = _match_partner(db, model, key[:length])
        if rows:
            return rows
    return []


def _stock_warehouse(
    db: Session, principal: Principal, product_id: int
) -> tuple[int, str] | None:
    """未指定仓库时，若该产品只在唯一一个有库存的仓库，就用它。"""
    rows = [
        row
        for row in inventory_service.list_inventory(db, principal)
        if row["product_id"] == product_id and Decimal(row["quantity"]) > 0
    ]
    if len({row["warehouse_id"] for row in rows}) != 1:
        return None
    return rows[0]["warehouse_id"], rows[0]["warehouse_name"]


def _handle_create(
    db: Session,
    principal: Principal,
    text: str,
    session_id: str | None,
) -> dict[str, Any]:
    try:
        parsed = llm.extract("business_order.v1.md", text, None)
    except llm.LLMError:
        return _reply(
            "没能理解要创建的单据。请说明：采购/销售/出库/入库、对方名称、产品名称和数量。"
        )
    action = str(parsed.get("action") or "").strip()
    if action not in ("create_purchase", "create_sales", "create_inbound", "create_outbound"):
        return _reply(
            "只支持创建采购、销售、入库、出库草稿，请说明单据类型、对方名称、产品、数量。"
        )

    items = parsed.get("items") or []
    if not items:
        return _reply("请补充至少一条产品明细（产品名称、数量、单价）。")
    # 模型偶尔会改写数字，单条明细时以原话中的吨数为准
    ton_numbers = re.findall(r"(\d+(?:\.\d+)?)\s*吨", text)
    if len(items) == 1 and len(ton_numbers) == 1:
        items[0]["quantity"] = ton_numbers[0]

    resolved_items: list[dict[str, Any]] = []
    desc_parts: list[str] = []
    for item in items:
        value = str(item.get("product") or item.get("product_name") or "").strip()
        if not value:
            return _reply("明细缺少产品名称。")
        products = _match_partner(db, Product, value)
        if len(products) != 1:
            names = "、".join(f"{p.code} {p.name}" for p in products) or "未找到"
            return _reply(f"产品“{value}”匹配到 {len(products)} 个（{names}），请写得更具体。")
        product = products[0]
        quantity = item.get("quantity")
        if quantity is None:
            return _reply(f"请补充产品 {product.name} 的数量。")
        unit_price = item.get("unit_price")
        if unit_price is None:
            unit_price = (
                product.purchase_price if action == "create_purchase" else product.sale_price
            )
        resolved_items.append(
            {
                "product_id": product.id,
                "quantity": quantity,
                "unit_price": str(unit_price),
            }
        )
        desc_parts.append(f"{product.name} {quantity}")

    if action in ("create_inbound", "create_outbound"):
        is_inbound = action == "create_inbound"
        movement_type = "inbound" if is_inbound else "outbound"
        partner_label = "供应商" if is_inbound else "客户"
        partner_model = Supplier if is_inbound else Customer
        partner_value = str(
            parsed.get("supplier" if is_inbound else "customer") or ""
        ).strip()

        partner = None
        approximate = False
        if partner_value:
            partners = _match_partner(db, partner_model, partner_value)
            if len(partners) > 1:
                names = "、".join(f"{p.code} {p.name}" for p in partners)
                return _reply(
                    f"{partner_label}“{partner_value}”匹配到 {len(partners)} 个（{names}），请写得更具体。"
                )
            if partners:
                partner = partners[0]
            else:
                similar = _similar_partners(db, partner_model, partner_value)
                if len(similar) == 1:
                    partner = similar[0]
                    approximate = True
                elif similar:
                    names = "、".join(f"{p.code} {p.name}" for p in similar)
                    return _reply(
                        f"系统里没有{partner_label}“{partner_value}”，相近的有：{names}。请指明是哪一个。"
                    )
                else:
                    return _reply(
                        f"系统里没有{partner_label}“{partner_value}”，请先在{partner_label}档案里创建，或换一个现有{partner_label}。"
                    )

        warehouse_name = str(parsed.get("warehouse") or "").strip()
        warehouse_id = None
        auto_note = ""
        warehouses = inventory_service.list_warehouses(db, principal)
        if warehouse_name:
            matched = [
                item
                for item in warehouses
                if warehouse_name in (item.get("name"), item.get("code"))
            ]
            if len(matched) != 1:
                names = "、".join(item["name"] for item in warehouses) or "无可用仓库"
                return _reply(
                    f"仓库“{warehouse_name}”匹配到 {len(matched)} 个（{names}），请指定仓库。"
                )
            warehouse_id = matched[0]["id"]
            warehouse_name = matched[0]["name"]
        elif len(warehouses) == 1:
            warehouse_id = warehouses[0]["id"]
            warehouse_name = warehouses[0]["name"]
        else:
            # 出库时按产品库存自动定位仓库；入库仍需用户指定
            picked = (
                None
                if is_inbound
                else _stock_warehouse(db, principal, resolved_items[0]["product_id"])
            )
            if picked:
                warehouse_id, warehouse_name = picked
                auto_note = "（该产品库存所在仓库）"
            else:
                names = "、".join(item["name"] for item in warehouses) or "无可用仓库"
                return _reply(f"请指定仓库：{names}。")

        remark_parts = []
        if partner is not None:
            remark_parts.append(f"{partner_label}：{partner.name}")
        if parsed.get("remark"):
            remark_parts.append(str(parsed["remark"]))
        remark = "；".join(remark_parts) or None

        label = "入库单草稿" if is_inbound else "出库单草稿"
        summary = f"创建{label}：{'、'.join(desc_parts)}"
        if warehouse_name:
            summary += f"，仓库 {warehouse_name}{auto_note}"
        if partner is not None:
            summary += f"，{partner_label} {partner.name}"
            if approximate:
                summary += "（按名称近似匹配）"
        return _confirm(
            db,
            principal,
            session_id,
            action="business.create_movement_draft",
            params={
                "movement_type": movement_type,
                "warehouse_id": warehouse_id,
                "remark": remark,
                "items": resolved_items,
            },
            summary=summary,
            prompt=f"将{summary}，确认执行吗？",
        )

    if action == "create_purchase":
        value = str(parsed.get("supplier") or "").strip()
        if not value:
            return _reply("请补充供应商名称。")
        partners = _match_partner(db, Supplier, value)
        if len(partners) != 1:
            names = "、".join(f"{p.code} {p.name}" for p in partners) or "未找到"
            return _reply(f"供应商“{value}”匹配到 {len(partners)} 个（{names}），请写得更具体。")
        params = {
            "supplier_id": partners[0].id,
            "order_date": parsed.get("order_date"),
            "remark": parsed.get("remark"),
            "items": resolved_items,
        }
        summary = f"创建采购草稿：供应商 {partners[0].name}，{len(resolved_items)} 条明细"
        tool_name = "business.create_purchase_draft"
        label = "采购草稿"
    else:
        value = str(parsed.get("customer") or "").strip()
        if not value:
            return _reply("请补充客户名称。")
        partners = _match_partner(db, Customer, value)
        if len(partners) != 1:
            names = "、".join(f"{p.code} {p.name}" for p in partners) or "未找到"
            return _reply(f"客户“{value}”匹配到 {len(partners)} 个（{names}），请写得更具体。")
        params = {
            "customer_id": partners[0].id,
            "order_date": parsed.get("order_date"),
            "remark": parsed.get("remark"),
            "items": resolved_items,
        }
        summary = f"创建销售草稿：客户 {partners[0].name}，{len(resolved_items)} 条明细"
        tool_name = "business.create_sales_draft"
        label = "销售草稿"

    return _confirm(
        db,
        principal,
        session_id,
        action=tool_name,
        params=params,
        summary=summary,
        prompt=f"将{summary}，确认执行吗？",
    )


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
    match = ORDER_NO_RE.search(text.upper())
    if match:
        return _handle_order(db, principal, text, match.group(0), session_id)

    if any(word in text for word in REMINDER_WORDS):
        return _handle_reminders(principal, text)

    if any(word in text for word in LIST_WORDS) or (
        ("采购单" in text or "销售单" in text)
        and not any(
            word in text for word in ("提交", "审核", "作废", "取消", "新建", "创建")
        )
    ):
        return _handle_list(principal, text)

    if "预警" in text:
        return _handle_alerts(db, principal, text, session_id)

    if "盘点" in text:
        return _handle_checks(principal, text)

    if any(word in text for word in ("客户", "供应商")) and any(
        word in text for word in ("档案", "信用", "资料", "欠款", "应收", "应付")
    ):
        return _handle_profile(principal, text)

    if any(word in text for word in PENDING_WORDS):
        ok, data, message = _tool("business.pending_tasks", {}, principal)
        if not ok:
            return _reply(message or "查询待办失败。")
        items = data.get("items") or []
        if not items:
            return _reply(f"{data.get('user') or '你'}当前没有待处理的单据。")
        lines = [f"{data.get('user') or '你'}当前有 {data['total']} 条待办："]
        for item in items[:10]:
            extra = f"，金额 {item['amount']}" if item.get("amount") else ""
            lines.append(f"- {item['kind']}：{item['doc_no']}{extra}")
        if data["total"] > 10:
            lines.append(f"（仅显示前 10 条，共 {data['total']} 条）")
        return _reply("\n".join(lines), sources=[{"type": "business", "name": "pending_tasks"}])

    if "库存" in text or "结存" in text:
        keyword = text
        for word in ("库存", "结存", "多少", "还有", "查询", "查一下", "现在"):
            keyword = keyword.replace(word, " ")
        keyword = keyword.strip(" ，。？?") or None
        ok, data, message = _tool(
            "business.stock_by_product", {"keyword": keyword}, principal
        )
        if not ok:
            return _reply(message or "查询库存失败。")
        rows = data.get("items") or []
        if not rows:
            return _reply(f"没有查到{('“' + keyword + '”') if keyword else ''}的库存记录。")
        lines = [f"库存合计 {data.get('quantity_total')}（{len(rows)} 个产品/仓库）："]
        for row in rows[:10]:
            lines.append(
                f"- {row.get('product_name')}：{row.get('quantity')} {row.get('unit') or ''}"
                f"（{row.get('warehouse_name') or ''}）"
            )
        return _reply("\n".join(lines), sources=[{"type": "business", "name": "stock"}])

    if "应收" in text or "应付" in text:
        record_type = "receivable" if "应收" in text else "payable"
        ok, data, message = _tool(
            "business.receivable_payable", {"record_type": record_type}, principal
        )
        if not ok:
            return _reply(message or "查询失败。")
        lines = [
            f"应收合计 {data.get('receivable_total')}，应付合计 {data.get('payable_total')}。"
        ]
        for item in (data.get("items") or [])[:10]:
            lines.append(
                f"- {item['record_date']} {item['counterparty_name'] or '-'}："
                f"{'应收' if item['record_type'] == 'receivable' else '应付'} {item['amount']}"
            )
        return _reply("\n".join(lines), sources=[{"type": "business", "name": "receivable"}])

    if any(word in text for word in CREATE_WORDS):
        return _handle_create(db, principal, text, session_id)

    return _reply(
        "可以这样问我：\n"
        "- 查采购单 PO000001 / 查销售单 SO000001\n"
        "- 我的待办 / 库存 煤\n"
        "- 应收应付情况 / 应收账龄\n"
        "- 有哪些预警 / 客户 华北能源 的档案\n"
        "- 盘点单情况\n"
        "- 新建采购草稿：供应商 XX，产品 XX 数量 10 单价 100\n"
        "- 新建出库草稿：给客户 XX 出 6000 吨精煤"
    )
