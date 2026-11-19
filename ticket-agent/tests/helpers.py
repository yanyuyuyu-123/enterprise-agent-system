"""测试共用：登录、建单请求体、SSE 解析。"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

PWD = "Dev@123456"

CATEGORY_DETAIL: dict[str, dict[str, Any]] = {
    "device_repair": {
        "description": "设备无法启动",
        "device": {"device_id": 1, "fault_description": "按下启动键无反应"},
    },
    "expense_reimbursement": {
        "description": "出差交通费",
        "expense": {"expense_type": "travel", "amount": 120.50},
    },
    "security_patrol": {
        "description": "东门巡查发现隐患",
        "patrol": {"patrol_area": "厂区东门", "hazard_description": "照明损坏"},
    },
    "transport_exception": {
        "description": "运输延误",
        "transport": {"trip_no": "TRIP-001", "exception_type": "delay"},
    },
}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def order_payload(
    category: str,
    *,
    complete: bool = True,
    title: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": category,
        "title": title or f"验收-{category}-{uuid4().hex[:8]}",
    }
    if complete:
        payload.update(CATEGORY_DETAIL[category])
    return payload


def create_order(client, token: str, category: str, **kwargs: Any):
    return client.post(
        "/api/v1/work_orders",
        json=order_payload(category, **kwargs),
        headers=auth(token),
    )


def chat(client, token: str, **payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    response = client.post("/api/v1/agent/chat", json=payload, headers=auth(token))
    assert response.status_code == 200, response.text
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    result = next((item for item in events if item["type"] == "result"), None)
    error = next((item for item in events if item["type"] == "error"), None)
    return events, result or error
