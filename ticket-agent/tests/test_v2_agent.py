"""T28–T30：Supervisor 路由、运营分析、模拟数据隔离。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.agents import finance_agent, llm, ops_agent, supervisor
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.org import User
from app.services.permission_service import Principal, load_principal
from tests.helpers import auth, chat, create_order


def ok(response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["code"] == 0, payload
    return payload["data"]


def fail(response, status_code: int, code: int) -> None:
    assert response.status_code == status_code, response.text
    assert response.json()["code"] == code, response.text


def _principal(employee_no: str) -> Principal:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.employee_no == employee_no))
        assert user is not None
        return load_principal(db, user)
    finally:
        db.close()


def test_t28_supervisor_routing() -> None:
    assert supervisor.route_domain("帮我建一个设备维修工单") == "work_order"
    assert supervisor.route_domain("差旅报销制度有什么规定") == "knowledge"
    assert supervisor.route_domain("本月库存和销售情况") == "operations"
    assert supervisor.route_domain("本月收入、成本和利润") == "finance"

    db = SessionLocal()
    try:
        result = supervisor.run(db, _principal("V2B01"), "帮我提交一张设备维修工单")
    finally:
        db.close()
    assert result["domain"] == "work_order"
    assert result["delegate"] == "work_order_agent"


def test_t29_operations_agent_composition() -> None:
    db = SessionLocal()
    try:
        result = supervisor.run(db, _principal("V2B01"), "本月库存和销售情况")
        partial = ops_agent.run(db, _principal("V2W01"), "本月库存和销售情况")
    finally:
        db.close()

    assert result["domain"] == "operations"
    assert result["status"] == "ok"
    assert 1 <= len(result["sources"]) <= 3
    assert result["missing"] == []
    assert result["answer"]

    # 缺少销售权限时说明缺失，而不是编造
    assert partial["status"] == "partial"
    assert any("销售" in item for item in partial["missing"])
    assert all(source["id"] != "sales" for source in partial["sources"])


def test_t30_mock_isolation_and_label(client, tokens, monkeypatch) -> None:
    # 非生产环境可写模拟数据
    created = ok(
        client.post(
            "/api/v1/finance-records",
            json={
                "record_type": "income",
                "amount": "88.00",
                "is_mock": True,
            },
            headers=auth(tokens("V2A01")),
        )
    )
    assert created["is_mock"] is True
    ok(
        client.post(
            f"/api/v1/finance-records/{created['id']}/review",
            json={"version": created["version"], "decision": "approve"},
            headers=auth(tokens("V2F01")),
        )
    )

    # Agent 结果标注模拟数据
    db = SessionLocal()
    try:
        result = finance_agent.run(db, _principal("V2F01"), "本月收入成本利润")
    finally:
        db.close()
    assert result["status"] == "ok"
    assert result["answer"].startswith("【模拟数据】")

    # 生产环境拒绝写入模拟数据
    monkeypatch.setattr(settings, "app_env", "prod")
    fail(
        client.post(
            "/api/v1/finance-records",
            json={"record_type": "income", "amount": "1.00", "is_mock": True},
            headers=auth(tokens("V2A01")),
        ),
        403,
        3000,
    )


def test_t31_chat_history(client, tokens) -> None:
    token = tokens("V2W01")
    _, result = chat(client, token, message="我负责的待处理工单有哪些？")
    assert result and result["type"] == "result", result
    sid = result["session_id"]

    sessions = ok(client.get("/api/v1/agent/sessions", headers=auth(token)))
    assert sid in [item["session_id"] for item in sessions]
    current = next(item for item in sessions if item["session_id"] == sid)
    assert current["title"]
    assert current["message_count"] >= 2

    detail = ok(client.get(f"/api/v1/agent/sessions/{sid}/messages", headers=auth(token)))
    roles = [item["role"] for item in detail["messages"]]
    assert "user" in roles and "assistant" in roles

    # 会话按账号隔离，别人看不到
    others = ok(client.get("/api/v1/agent/sessions", headers=auth(tokens("V2B01"))))
    assert sid not in [item["session_id"] for item in others]


def test_t32_domain_followup_keeps_context(client, tokens) -> None:
    token = tokens("V2A01")
    _, first = chat(client, token, message="公司目前资金有多少？")
    assert first and first["intent"] == "finance_query", first
    sid = first["session_id"]

    # 没有领域关键词的追问应继承上一轮的财务领域，而不是被判成“没太理解”
    _, second = chat(client, token, message="这么少吗", session_id=sid)
    assert second and second["intent"] == "finance_query", second
    assert "没太理解" not in second["answer"]


def test_t33_capability_intro(client, tokens) -> None:
    token = tokens("V2A01")
    _, result = chat(client, token, message="你能介绍一下你自己吗")
    assert result and "企业智能助手" in result["answer"], result

    # 有历史时问“那你是谁”不能掉回上一轮的财务回答
    _, follow = chat(client, token, message="那你是谁", session_id=result["session_id"])
    assert follow and "企业智能助手" in follow["answer"], follow


def test_t34_off_topic_refused(client, tokens) -> None:
    if not llm.available():
        pytest.skip("未配置 DEEPSEEK_API_KEY，无法判断问题范围")
    token = tokens("V2A01")
    _, result = chat(client, token, message="今天天气怎么样？")
    assert result and result["answer"].startswith("与公司无关"), result


def test_t35_business_order_agent(client, tokens) -> None:
    from app.agents import business_agent
    from uuid import uuid4

    assert supervisor.route_domain("查采购单 PO000001") == "business"
    assert supervisor.route_domain("我的待办有哪些") == "business"
    assert supervisor.route_domain("本月采购汇总") == "operations"

    supplier = ok(
        client.post(
            "/api/v1/suppliers",
            json={"code": f"SUP{uuid4().hex[:8]}", "name": "Agent供应商"},
            headers=auth(tokens("V2P01")),
        )
    )
    product = ok(
        client.post(
            "/api/v1/products",
            json={
                "code": f"PRD{uuid4().hex[:8]}",
                "name": "Agent产品",
                "purchase_price": "12.00",
                "sale_price": "20.00",
            },
            headers=auth(tokens("V2M01")),
        )
    )
    order = ok(
        client.post(
            "/api/v1/purchase-orders",
            json={
                "supplier_id": supplier["id"],
                "items": [
                    {"product_id": product["id"], "quantity": "3", "unit_price": "12.00"}
                ],
            },
            headers=auth(tokens("V2P01")),
        )
    )

    # 按单号查详情走 business 域，且复用业务口径
    _, detail = chat(client, tokens("V2P01"), message=f"查采购单 {order['order_no']}")
    assert detail and detail["intent"] == "business_query", detail
    assert order["order_no"] in detail["answer"]
    assert "草稿" in detail["answer"]

    # 提交是写操作：先返回确认卡片，确认后才执行
    _, pending = chat(client, tokens("V2P01"), message=f"提交采购单 {order['order_no']}")
    assert pending and pending["confirmation"], pending
    _, done = chat(
        client,
        tokens("V2P01"),
        confirm_token=pending["confirmation"]["confirm_token"],
    )
    assert done and "已提交" in done["answer"], done

    db = SessionLocal()
    try:
        result = supervisor.run(db, _principal("V2P01"), f"查采购单 {order['order_no']}")
        assert result["domain"] == "business"
        assert "待审核" in result["answer"]
        tasks = business_agent.run(db, _principal("V2B01"), "我的待办")
        assert result["status"] == "ok"
        assert order["order_no"] in tasks["answer"]
    finally:
        db.close()


def test_t36_business_list_reminder_update_cancel(client, tokens) -> None:
    from uuid import uuid4

    from app.agents import business_agent
    from app.services import purchase_service
    from app.tools.executor import execute_tool

    supplier = ok(
        client.post(
            "/api/v1/suppliers",
            json={"code": f"SUP{uuid4().hex[:8]}", "name": "列表供应商"},
            headers=auth(tokens("V2P01")),
        )
    )
    product = ok(
        client.post(
            "/api/v1/products",
            json={
                "code": f"PRD{uuid4().hex[:8]}",
                "name": "列表产品",
                "purchase_price": "12.00",
                "sale_price": "20.00",
            },
            headers=auth(tokens("V2M01")),
        )
    )
    draft = ok(
        client.post(
            "/api/v1/purchase-orders",
            json={
                "supplier_id": supplier["id"],
                "items": [
                    {"product_id": product["id"], "quantity": "3", "unit_price": "12.00"}
                ],
            },
            headers=auth(tokens("V2P01")),
        )
    )

    db = SessionLocal()
    try:
        principal = _principal("V2P01")
        listed_result, _ = execute_tool(
            "business.purchase_order_list",
            {"supplier_id": supplier["id"], "page_size": 50},
            principal,
        )
        assert listed_result["ok"], listed_result
        listed = listed_result["data"]
        assert any(item["order_no"] == draft["order_no"] for item in listed["items"])

        detail = purchase_service.get_purchase_order(db, principal, draft["id"])
        new_items = [
            {
                "product_id": item["product_id"],
                "quantity": "5",
                "unit_price": item["unit_price"],
            }
            for item in detail["items"]
        ]
        updated_result, _ = execute_tool(
            "business.update_order",
            {
                "order_type": "purchase",
                "order_id": draft["id"],
                "version": detail["version"],
                "items": new_items,
            },
            principal,
        )
        assert updated_result["ok"], updated_result
        updated = updated_result["data"]
        assert updated["total_amount"] == "60.00"

        cancel_result, _ = execute_tool(
            "business.cancel_order",
            {
                "order_type": "purchase",
                "order_id": draft["id"],
                "version": updated["version"],
                "reason": "测试取消",
            },
            _principal("V2B01"),
        )
        assert cancel_result["ok"], cancel_result
        assert cancel_result["data"]["status"] == "void"

        # 已审核未入库的订单出现在履约提醒里
        order = ok(
            client.post(
                "/api/v1/purchase-orders",
                json={
                    "supplier_id": supplier["id"],
                    "items": [
                        {"product_id": product["id"], "quantity": "2", "unit_price": "12.00"}
                    ],
                },
                headers=auth(tokens("V2P01")),
            )
        )
        submitted = ok(
            client.post(
                f"/api/v1/purchase-orders/{order['id']}/submit",
                json={"version": order["version"]},
                headers=auth(tokens("V2P01")),
            )
        )
        ok(
            client.post(
                f"/api/v1/purchase-orders/{order['id']}/review",
                json={"version": submitted["version"], "decision": "approve"},
                headers=auth(tokens("V2B01")),
            )
        )
        reminder_result, _ = execute_tool(
            "business.fulfillment_reminders", {"order_type": "purchase"}, principal
        )
        assert reminder_result["ok"], reminder_result
        reminders = reminder_result["data"]
        target = next(
            item for item in reminders["items"] if item["order_no"] == order["order_no"]
        )
        assert target["lines"][0]["remaining_quantity"] == "2.000"

        answer = business_agent.run(db, principal, "哪些采购单还没入库")
        assert order["order_no"] in answer["answer"]
    finally:
        db.close()


def test_t37_finance_aging_and_cash_flow(client, tokens) -> None:
    from uuid import uuid4

    from app.agents import finance_agent
    from app.tools.executor import execute_tool

    customer = ok(
        client.post(
            "/api/v1/customers",
            json={"code": f"CUS{uuid4().hex[:8]}", "name": "账龄客户"},
            headers=auth(tokens("V2S01")),
        )
    )
    receivable = ok(
        client.post(
            "/api/v1/finance-records",
            json={
                "record_type": "receivable",
                "amount": "1200.00",
                "counterparty_type": "customer",
                "counterparty_id": customer["id"],
            },
            headers=auth(tokens("V2F01")),
        )
    )
    assert receivable["status"] == "approved"

    db = SessionLocal()
    try:
        principal = _principal("V2F01")
        aging_result, _ = execute_tool("finance.aging", {}, principal)
        assert aging_result["ok"], aging_result
        aging = aging_result["data"]
        assert Decimal(aging["receivable"]["0-30"]) >= Decimal("1200.00")
        target = next(
            item for item in aging["items"] if item["counterparty_id"] == customer["id"]
        )
        assert target["counterparty_name"] == "账龄客户"
        assert target["record_type"] == "receivable"

        flow_result, _ = execute_tool(
            "finance.create_cash_flow",
            {"direction": "in", "amount": "500.00", "payment_method": "银行"},
            principal,
        )
        assert flow_result["ok"], flow_result
        flow = flow_result["data"]
        assert flow["status"] == "approved"

        listed, _ = execute_tool(
            "finance.cash_flow_list", {"direction": "in", "page_size": 50}, principal
        )
        assert listed["ok"], listed
        assert any(item["flow_no"] == flow["flow_no"] for item in listed["data"]["items"])

        aging_answer = finance_agent.run(db, principal, "应收账龄")
        assert "账龄" in aging_answer["answer"]

        flow_answer = finance_agent.run(db, principal, "本月资金流水")
        assert flow["flow_no"] in flow_answer["answer"]
    finally:
        db.close()

    # 登记收付款走二次确认
    _, pending = chat(client, tokens("V2F01"), message="登记收款 800 元，现金")
    assert pending and pending["confirmation"], pending
    _, done = chat(
        client,
        tokens("V2F01"),
        confirm_token=pending["confirmation"]["confirm_token"],
    )
    assert done and "已登记" in done["answer"], done


def test_t38_crm_profile_and_alert_acknowledge(client, tokens) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.models.alert import Alert
    from app.tools.executor import execute_tool

    customer_name = f"档案客户{uuid4().hex[:6]}"
    customer = ok(
        client.post(
            "/api/v1/customers",
            json={
                "code": f"CUS{uuid4().hex[:8]}",
                "name": customer_name,
                "credit_limit": "5000.00",
            },
            headers=auth(tokens("V2S01")),
        )
    )
    ok(
        client.post(
            "/api/v1/finance-records",
            json={
                "record_type": "receivable",
                "amount": "800.00",
                "counterparty_type": "customer",
                "counterparty_id": customer["id"],
            },
            headers=auth(tokens("V2F01")),
        )
    )

    alert_no = f"AL2026{uuid4().int % 10**8:08d}"
    db = SessionLocal()
    try:
        alert = Alert(
            alert_no=alert_no,
            alert_type="low_stock",
            level="warning",
            target_type="product",
            target_id=0,
            department_id=3,
            title="测试库存预警",
            content="低于安全库存",
            dedupe_key=f"test:{uuid4()}",
            triggered_at=datetime.now(UTC),
        )
        db.add(alert)
        db.commit()

        principal = _principal("V2S01")
        result, _ = execute_tool(
            "crm.customer_profile", {"keyword": customer_name}, principal
        )
        assert result["ok"], result
        profile = result["data"]
        assert profile["receivable_total"] == "800.00"
        assert Decimal(profile["credit_available"]) == Decimal("5000.00") - Decimal("800.00")

        wh = _principal("V2W01")
        listed, _ = execute_tool("wms.alert_list", {"status": "open", "page_size": 50}, wh)
        assert listed["ok"], listed
        assert any(
            item["alert_no"] == alert_no for item in listed["data"]["items"]
        ), listed
    finally:
        db.close()

    _, profile_answer = chat(
        client, tokens("V2S01"), message=f"查客户 {customer_name} 的档案"
    )
    assert profile_answer and "累计应收" in profile_answer["answer"], profile_answer

    _, pending = chat(client, tokens("V2W01"), message=f"认领预警 {alert_no}")
    assert pending and pending["confirmation"], pending
    _, done = chat(
        client,
        tokens("V2W01"),
        confirm_token=pending["confirmation"]["confirm_token"],
    )
    assert done and "已认领" in done["answer"], done


def test_t39_work_order_review_by_agent(client, tokens, db) -> None:
    from app.agents import rules

    assert rules.detect_intent("审核通过 WO202611100001") == "work_order_review"
    extracted = rules.extract("work_order_review", "驳回 WO202611100001，照片不清晰")
    assert extracted["decision"] == "reject"
    assert extracted["comment"] == "照片不清晰"

    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    assignee_id = db.scalar(select(User.id).where(User.employee_no == "R0001"))
    assigned = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/assign",
            json={"version": created["version"], "assignee_id": assignee_id},
            headers=auth(tokens("P0001")),
        )
    )
    started = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/start",
            json={"version": assigned["version"]},
            headers=auth(tokens("R0001")),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/submit",
            json={
                "version": started["version"],
                "content": "已更换启动器",
                "repair_result": "更换后正常",
            },
            headers=auth(tokens("R0001")),
        )
    )
    assert submitted["status"] == "pending_review"
    reviewer = db.scalar(select(User.employee_no).where(User.id == submitted["reviewer_id"]))
    assert reviewer

    _, pending = chat(
        client, tokens(reviewer), message=f"审核通过 {submitted['order_no']}"
    )
    assert pending and pending["confirmation"], pending
    _, done = chat(
        client,
        tokens(reviewer),
        confirm_token=pending["confirmation"]["confirm_token"],
    )
    assert done and "审核完成" in done["answer"], done
    assert "已完成" in done["answer"]


def test_t40_agent_create_outbound_draft(client, tokens, monkeypatch) -> None:
    """自然语言建出库单：客户名写错也能近似匹配，6000 吨不被改写，确认后生成草稿。"""
    from uuid import uuid4

    from app.agents import business_agent

    assert supervisor.route_domain("帮我创建一个出库单") == "business"

    warehouses = ok(client.get("/api/v1/warehouses", headers=auth(tokens("V2M01"))))
    assert warehouses
    warehouse_name = warehouses[0]["name"]
    product_name = f"精煤{uuid4().hex[:6]}"
    ok(
        client.post(
            "/api/v1/products",
            json={
                "code": f"PRD{uuid4().hex[:8]}",
                "name": product_name,
                "purchase_price": "100.00",
                "sale_price": "200.00",
            },
            headers=auth(tokens("V2M01")),
        )
    )
    customer_name = f"浙能{uuid4().hex[:4]}热电有限公司"
    ok(
        client.post(
            "/api/v1/customers",
            json={"code": f"CUS{uuid4().hex[:8]}", "name": customer_name},
            headers=auth(tokens("V2M01")),
        )
    )

    # 故意把客户名写错一个字，验证近似匹配后仍能出确认卡
    typed_name = customer_name.replace("热电", "热点")

    def fake_extract(_name: str, _text: str, _history: Any = None) -> dict[str, Any]:
        return {
            "action": "create_outbound",
            "supplier": None,
            "customer": typed_name,
            "warehouse": warehouse_name,
            "order_date": None,
            "remark": None,
            "items": [{"product": product_name, "quantity": 6000, "unit_price": None}],
        }

    monkeypatch.setattr(business_agent.llm, "extract", fake_extract)

    _, pending = chat(
        client,
        tokens("V2M01"),
        message=f"帮我创建一个出库单，在{warehouse_name}给客户{typed_name}出6000吨{product_name}",
    )
    assert pending and pending.get("confirmation"), pending
    summary = pending["confirmation"]["summary"]
    assert "6000" in summary and product_name in summary, summary
    assert customer_name in summary and "近似匹配" in summary, summary
    assert summary.startswith("创建出库单草稿"), summary
    assert pending["confirmation"]["params"]["movement_type"] == "outbound"

    _, done = chat(
        client,
        tokens("V2M01"),
        confirm_token=pending["confirmation"]["confirm_token"],
    )
    assert done and "已创建" in done["answer"], done
    assert "SM" in done["answer"], done


def test_t41_create_movement_draft_defaults_manual_source(client, tokens) -> None:
    """工具未传 source_type 时默认 manual，不再触发 Pydantic 校验失败。"""
    from uuid import uuid4

    from app.tools.executor import execute_tool

    warehouses = ok(client.get("/api/v1/warehouses", headers=auth(tokens("V2M01"))))
    product = ok(
        client.post(
            "/api/v1/products",
            json={
                "code": f"PRD{uuid4().hex[:8]}",
                "name": f"默认来源产品{uuid4().hex[:6]}",
                "purchase_price": "10.00",
                "sale_price": "20.00",
            },
            headers=auth(tokens("V2M01")),
        )
    )
    result, _meta = execute_tool(
        "business.create_movement_draft",
        {
            "movement_type": "outbound",
            "warehouse_id": warehouses[0]["id"],
            "items": [{"product_id": product["id"], "quantity": "5"}],
        },
        _principal("V2M01"),
        timeout_s=10,
    )
    assert result["ok"], result
    assert result["data"]["source_type"] == "manual", result["data"]
    assert result["data"]["status"] == "draft", result["data"]

