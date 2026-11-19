"""V1 验收用例 T01–T15（development_rules.md 第 10 章）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.main import app
from app.models.org import User
from app.models.work_order import (
    WorkOrder,
    WorkOrderDevice,
    WorkOrderExpense,
    WorkOrderPatrol,
    WorkOrderRecord,
    WorkOrderTransport,
)
from app.tasks.overdue import mark_overdue_orders
from tests.helpers import PWD, auth, chat, create_order

DETAIL_MODELS = {
    "device_repair": WorkOrderDevice,
    "expense_reimbursement": WorkOrderExpense,
    "security_patrol": WorkOrderPatrol,
    "transport_exception": WorkOrderTransport,
}


def ok(response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def fail(response, status: int, code: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code, body
    return body


def detail(client, token: str, order_id: int) -> dict[str, Any]:
    return ok(client.get(f"/api/v1/work_orders/{order_id}", headers=auth(token)))


def assign(client, token: str, order_id: int, version: int, assignee_id: int):
    return client.post(
        f"/api/v1/work_orders/{order_id}/assign",
        json={"version": version, "assignee_id": assignee_id},
        headers=auth(token),
    )


def user_id(db, employee_no: str) -> int:
    return db.scalar(select(User.id).where(User.employee_no == employee_no))


def employee_of(db, user_id_value: int) -> str:
    return db.scalar(select(User.employee_no).where(User.id == user_id_value))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def close_hours(actual: datetime, base: datetime, hours: int) -> bool:
    return abs((actual - base).total_seconds() - hours * 3600) < 120


def test_t01_login(client, tokens) -> None:
    assert tokens("W0001")

    bad = client.post("/api/v1/auth/login", json={"employee_no": "W0001", "password": "wrong-pass"})
    fail(bad, 401, 2000)

    disabled = client.post("/api/v1/auth/login", json={"employee_no": "D0001", "password": PWD})
    fail(disabled, 403, 2003)


def test_t02_create_four_categories(client, tokens, db) -> None:
    cases = [
        ("device_repair", "W0001", "pending_assignment"),
        ("expense_reimbursement", "W0001", "pending_process"),
        ("security_patrol", "G0001", "pending_assignment"),
        ("transport_exception", "T0001", "pending_assignment"),
    ]
    for category, employee_no, expected in cases:
        data = ok(create_order(client, tokens(employee_no), category))
        assert data["status"] == expected, data
        assert data["order_no"].startswith("WO"), data
        model = DETAIL_MODELS[category]
        count = db.scalar(
            select(func.count()).select_from(model).where(model.work_order_id == data["id"])
        )
        assert count == 1, f"{category} 明细应有且仅有一条"

    incomplete = ok(create_order(client, tokens("W0001"), "device_repair", complete=False))
    assert incomplete["status"] == "supplementing"
    assert incomplete["order_no"].startswith("WO")

    wrong = create_order(client, tokens("W0001"), "security_patrol")
    fail(wrong, 403, 3000)


def test_t03_expense_skips_assignment(client, tokens) -> None:
    data = ok(create_order(client, tokens("W0001"), "expense_reimbursement"))
    assert data["status"] == "pending_process"
    assert data["assignee_id"] == data["creator_id"]
    assert close_hours(dt(data["due_at"]), dt(data["assigned_at"]), 72)
    assert "assign" not in [row["action"] for row in data["records"]]


def test_t04_assign_and_reassign(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    order_id = created["id"]
    repairman = user_id(db, "R0001")
    repairman2 = user_id(db, "R0002")
    guard = user_id(db, "G0001")

    fail(assign(client, tokens("W0001"), order_id, created["version"], repairman), 403, 2001)
    fail(assign(client, tokens("P0001"), order_id, created["version"], guard), 400, 3006)

    assigned = ok(assign(client, tokens("P0001"), order_id, created["version"], repairman))
    assert assigned["status"] == "pending_process"
    assert assigned["assignee_id"] == repairman
    assert close_hours(dt(assigned["due_at"]), dt(assigned["assigned_at"]), 24)

    reassign = client.post(
        f"/api/v1/work_orders/{order_id}/reassign",
        json={"version": assigned["version"], "assignee_id": repairman2},
        headers=auth(tokens("P0001")),
    )
    reassigned = ok(reassign)
    assert reassigned["assignee_id"] == repairman2
    actions = [row["action"] for row in reassigned["records"]]
    assert "assign" in actions and "reassign" in actions


def test_t05_start_submit_approve(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    order_id = created["id"]
    reviewer = employee_of(db, created["reviewer_id"])
    assert reviewer in {"P0001", "P0002"}

    assigned = ok(
        assign(client, tokens("P0001"), order_id, created["version"], user_id(db, "R0001"))
    )
    started = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/start",
            json={"version": assigned["version"]},
            headers=auth(tokens("R0001")),
        )
    )
    assert started["status"] == "processing"

    submitted = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/submit",
            json={
                "version": started["version"],
                "content": "已更换启动器",
                "repair_result": "更换启动器后正常",
            },
            headers=auth(tokens("R0001")),
        )
    )
    assert submitted["status"] == "pending_review"

    reviewed = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": submitted["version"], "result": "approve"},
            headers=auth(tokens(reviewer)),
        )
    )
    assert reviewed["status"] == "completed"
    assert reviewed["completed_at"] is not None
    assert [row["action"] for row in reviewed["records"]] == [
        "create",
        "assign",
        "start",
        "submit_result",
        "review_approve",
    ]
    assert len(reviewed["approvals"]) == 1
    assert reviewed["approvals"][0]["result"] == "approved"


def _to_pending_review(client, tokens, db) -> dict[str, Any]:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    assigned = ok(
        assign(client, tokens("P0001"), created["id"], created["version"], user_id(db, "R0001"))
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
                "content": "处理完成",
                "repair_result": "已修复",
            },
            headers=auth(tokens("R0001")),
        )
    )
    submitted["reviewer"] = employee_of(db, created["reviewer_id"])
    return submitted


def test_t06_review_reject(client, tokens, db) -> None:
    order = _to_pending_review(client, tokens, db)
    order_id = order["id"]
    reviewer = order["reviewer"]

    fail(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": order["version"], "result": "reject"},
            headers=auth(tokens(reviewer)),
        ),
        422,
        1001,
    )

    rejected = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": order["version"], "result": "reject", "comment": "结果不完整"},
            headers=auth(tokens(reviewer)),
        )
    )
    assert rejected["status"] == "rejected"
    assert rejected["due_at"] == order["due_at"]
    assert rejected["approvals"][-1]["result"] == "rejected"

    revised = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/revise",
            json={
                "version": rejected["version"],
                "title": "设备故障维修（已修改）",
                "description": "设备无法启动，已补充故障现象",
            },
            headers=auth(tokens("W0001")),
        )
    )
    assert revised["status"] == "pending_review"
    assert revised["title"] == "设备故障维修（已修改）"
    assert revised["records"][-1]["action"] == "revise"
    assert revised["submitted_at"] is not None

    reapproved = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": revised["version"], "result": "approve"},
            headers=auth(tokens(reviewer)),
        )
    )
    assert reapproved["status"] == "completed"
    assert [row["result"] for row in reapproved["approvals"]] == ["rejected", "approved"]


def test_t07_recall(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    recalled = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/recall",
            json={"version": created["version"], "reason": "信息填错了"},
            headers=auth(tokens("W0001")),
        )
    )
    assert recalled["status"] == "cancelled"
    assert recalled["recall_reason"] == "信息填错了"

    incomplete = ok(create_order(client, tokens("W0001"), "device_repair", complete=False))
    fail(
        client.post(
            f"/api/v1/work_orders/{incomplete['id']}/recall",
            json={"version": incomplete["version"], "reason": "不需要了"},
            headers=auth(tokens("W0001")),
        ),
        409,
        3001,
    )

    started_order = ok(create_order(client, tokens("W0001"), "device_repair"))
    assigned = ok(
        assign(
            client,
            tokens("P0001"),
            started_order["id"],
            started_order["version"],
            user_id(db, "R0001"),
        )
    )
    started = ok(
        client.post(
            f"/api/v1/work_orders/{started_order['id']}/start",
            json={"version": assigned["version"]},
            headers=auth(tokens("R0001")),
        )
    )
    fail(
        client.post(
            f"/api/v1/work_orders/{started_order['id']}/recall",
            json={"version": started["version"], "reason": "不做了"},
            headers=auth(tokens("W0001")),
        ),
        409,
        3001,
    )


def test_t08_transfer(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    order_id = created["id"]
    reviewer = employee_of(db, created["reviewer_id"])
    assigned = ok(
        assign(client, tokens("P0001"), order_id, created["version"], user_id(db, "R0001"))
    )

    requested = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/transfer",
            json={"version": assigned["version"], "transfer_to_id": user_id(db, "R0002")},
            headers=auth(tokens("R0001")),
        )
    )
    assert requested["status"] == "pending_process"
    assert requested["transfer_status"] == "pending"
    assert requested["assignee_id"] == user_id(db, "R0001")

    approved = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/transfer/decision",
            json={"version": requested["version"], "approve": True},
            headers=auth(tokens(reviewer)),
        )
    )
    assert approved["status"] == "pending_process"
    assert approved["assignee_id"] == user_id(db, "R0002")
    assert dt(approved["due_at"]) > dt(assigned["due_at"])


def test_t09_illegal_transition(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    assert created["status"] == "pending_assignment"
    fail(
        client.post(
            f"/api/v1/work_orders/{created['id']}/review",
            json={"version": created["version"], "result": "approve"},
            headers=auth(tokens("P0001")),
        ),
        409,
        3001,
    )


def test_t10_optimistic_lock(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    first = ok(
        assign(
            client,
            tokens("P0001"),
            created["id"],
            created["version"],
            user_id(db, "R0001"),
        )
    )
    assert first["version"] == created["version"] + 1
    fail(
        assign(
            client,
            tokens("P0001"),
            created["id"],
            created["version"],
            user_id(db, "R0002"),
        ),
        409,
        3002,
    )


def test_t11_data_scope(client, tokens, db) -> None:
    worker = user_id(db, "W0001")
    own = ok(create_order(client, tokens("W0001"), "device_repair"))
    expense = ok(create_order(client, tokens("F0001"), "expense_reimbursement"))
    patrol = ok(create_order(client, tokens("G0001"), "security_patrol"))

    worker_items = ok(
        client.get("/api/v1/work_orders?page_size=100", headers=auth(tokens("W0001")))
    )["items"]
    assert worker_items
    assert all(
        item["creator_id"] == worker or item["assignee_id"] == worker for item in worker_items
    )

    department_items = ok(
        client.get("/api/v1/work_orders?page_size=100", headers=auth(tokens("P0001")))
    )["items"]
    assert department_items
    assert all(item["department_id"] == 4 for item in department_items)

    finance_items = ok(
        client.get("/api/v1/work_orders?page_size=100", headers=auth(tokens("F0001")))
    )["items"]
    assert finance_items
    assert all(item["category"] == "expense_reimbursement" for item in finance_items)

    all_items = ok(client.get("/api/v1/work_orders?page_size=100", headers=auth(tokens("M0001"))))[
        "items"
    ]
    ids = {item["id"] for item in all_items}
    assert {own["id"], expense["id"], patrol["id"]} <= ids


def test_t12_forbidden(client, tokens, db) -> None:
    own = ok(create_order(client, tokens("W0001"), "device_repair"))
    fail(
        assign(client, tokens("W0001"), own["id"], own["version"], user_id(db, "R0001")),
        403,
        2001,
    )
    fail(
        client.post(
            f"/api/v1/work_orders/{own['id']}/review",
            json={"version": own["version"], "result": "approve"},
            headers=auth(tokens("W0001")),
        ),
        403,
        2001,
    )

    hidden = ok(create_order(client, tokens("G0001"), "security_patrol"))
    fail(
        client.get(f"/api/v1/work_orders/{hidden['id']}", headers=auth(tokens("W0001"))),
        404,
        3003,
    )


def test_t13_overdue_scan(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    assigned = ok(
        assign(client, tokens("P0001"), created["id"], created["version"], user_id(db, "R0001"))
    )
    order = db.get(WorkOrder, created["id"])
    order.due_at = datetime.fromisoformat(assigned["due_at"]).replace(year=2020)
    db.commit()

    result = mark_overdue_orders.apply()
    assert result.state == "SUCCESS"
    assert result.get()["marked"] >= 1

    overdue = detail(client, tokens("W0001"), created["id"])
    assert overdue["is_overdue"] is True
    assert overdue["overdue_at"] is not None

    started = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/start",
            json={"version": overdue["version"]},
            headers=auth(tokens("R0001")),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/work_orders/{created['id']}/submit",
            json={
                "version": started["version"],
                "content": "超时后仍可提交",
                "repair_result": "已修复",
            },
            headers=auth(tokens("R0001")),
        )
    )
    assert submitted["status"] == "pending_review"


def test_t14_logs(client, tokens, db) -> None:
    created = ok(create_order(client, tokens("W0001"), "device_repair"))
    ok(assign(client, tokens("P0001"), created["id"], created["version"], user_id(db, "R0001")))

    logs = ok(
        client.get(
            "/api/v1/logs/operation?action=assign&log_level=important",
            headers=auth(tokens("M0001")),
        )
    )["items"]
    assert any(item["target_id"] == created["order_no"] for item in logs)

    expense_logs = ok(
        client.get(
            f"/api/v1/logs/operation?action=create&target_id={created['order_no']}",
            headers=auth(tokens("M0001")),
        )
    )["items"]
    assert expense_logs
    assert all("amount" not in item["detail"] for item in expense_logs)

    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/v1/logs"):
            methods |= set(getattr(route, "methods", set()))
    assert methods <= {"GET", "HEAD"}


def test_t15_agent_create(client, tokens, db) -> None:
    before = db.scalar(select(func.count()).select_from(WorkOrder))

    events, result = chat(client, tokens("W0001"), message="设备 DEV-001 无法启动，帮我报修")
    assert result is not None, events
    assert result["intent"] == "work_order_create"
    assert result["confirmation"], result

    pending = db.scalar(select(func.count()).select_from(WorkOrder))
    assert pending == before

    _, confirmed = chat(
        client, tokens("W0001"), confirm_token=result["confirmation"]["confirm_token"]
    )
    assert confirmed is not None
    order_no = confirmed["tool_result"]["data"]["order_no"]

    after = db.scalar(select(func.count()).select_from(WorkOrder))
    assert after == before + 1

    order = db.scalar(select(WorkOrder).where(WorkOrder.order_no == order_no))
    record = db.scalar(
        select(WorkOrderRecord).where(
            WorkOrderRecord.work_order_id == order.id,
            WorkOrderRecord.action == "create",
        )
    )
    assert record is not None
    assert record.is_agent is True


@pytest.mark.parametrize("path", ["/api/v1/logs/operation", "/api/v1/logs/agent"])
def test_t14_log_endpoints_are_read_only(client, tokens, path: str) -> None:
    response = client.delete(path, headers=auth(tokens("M0001")))
    assert response.status_code == 405
