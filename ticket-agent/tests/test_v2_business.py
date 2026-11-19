"""V2 验收用例（development_rules.md 13.13）。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.business import CashFlow, FinanceRecord, StockMovement
from app.models.org import User
from app.services import metric_service
from tests.helpers import auth, create_order


def ok(response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def fail(response, status: int, code: int) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def auth_headers(tokens, employee_no: str) -> dict[str, str]:
    return auth(tokens(employee_no))


def test_t16_master_data_crud_and_permission(client, tokens) -> None:
    code = f"SUP{uuid4().hex[:8]}"
    payload = {"code": code, "name": "测试供应商", "payment_type": "credit"}

    created = ok(
        client.post(
            "/api/v1/suppliers",
            json=payload,
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    assert created["code"] == code
    assert created["payment_type"] == "credit"

    # 采购员无客户创建权限
    fail(
        client.post(
            "/api/v1/customers",
            json={"code": f"CUS{uuid4().hex[:8]}", "name": "测试客户"},
            headers=auth_headers(tokens, "V2P01"),
        ),
        403,
        2001,
    )

    # 重复编码
    fail(
        client.post(
            "/api/v1/suppliers",
            json=payload,
            headers=auth_headers(tokens, "V2P01"),
        ),
        409,
        3000,
    )

    # 业务员只能看到本人客户
    customer_code = f"CUS{uuid4().hex[:8]}"
    ok(
        client.post(
            "/api/v1/customers",
            json={"code": customer_code, "name": "业务员客户"},
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    own = ok(
        client.get(
            f"/api/v1/customers?keyword={customer_code}",
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    assert own["total"] == 1
    fail(
        client.get(
            f"/api/v1/customers?keyword={customer_code}",
            headers=auth_headers(tokens, "V2P01"),
        ),
        403,
        2001,
    )

    # 无主数据权限的岗位
    fail(
        client.get("/api/v1/suppliers", headers=auth_headers(tokens, "V2K01")),
        403,
        2001,
    )


def _create_product(client, tokens) -> int:
    data = ok(
        client.post(
            "/api/v1/products",
            json={
                "code": f"PRD{uuid4().hex[:8]}",
                "name": "测试产品",
                "purchase_price": "10.00",
                "sale_price": "20.00",
            },
            headers=auth_headers(tokens, "V2M01"),
        )
    )
    return data["id"]


def _finance(source_type: str, source_id: int) -> list[FinanceRecord]:
    db = SessionLocal()
    try:
        return list(
            db.scalars(
                select(FinanceRecord).where(
                    FinanceRecord.source_type == source_type,
                    FinanceRecord.source_id == source_id,
                )
            ).all()
        )
    finally:
        db.close()


def test_t17_purchase_order_flow_and_finance(client, tokens) -> None:
    supplier = ok(
        client.post(
            "/api/v1/suppliers",
            json={"code": f"SUP{uuid4().hex[:8]}", "name": "采购供应商"},
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    product_id = _create_product(client, tokens)
    order = ok(
        client.post(
            "/api/v1/purchase-orders",
            json={
                "supplier_id": supplier["id"],
                "items": [{"product_id": product_id, "quantity": "2", "unit_price": "10.50"}],
            },
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    assert order["status"] == "draft"
    assert order["total_amount"] == "21.00"

    submitted = ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/submit",
            json={"version": order["version"]},
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    assert submitted["status"] == "pending_review"

    # 采购员无审核权限
    fail(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/review",
            json={"version": submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2P01"),
        ),
        403,
        2001,
    )

    approved = ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/review",
            json={"version": submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    assert approved["status"] == "approved"

    records = _finance("purchase_order", order["id"])
    assert [(r.record_type, str(r.amount), r.status) for r in records] == [
        ("payable", "21.00", "approved")
    ]

    voided = ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/void",
            json={"version": approved["version"], "reason": "供应商取消"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    assert voided["status"] == "void"
    assert all(record.status == "void" for record in _finance("purchase_order", order["id"]))

    # 采购入库审核后生成成本（采购单不 void）
    order2 = ok(
        client.post(
            "/api/v1/purchase-orders",
            json={
                "supplier_id": supplier["id"],
                "items": [{"product_id": product_id, "quantity": "2", "unit_price": "10.50"}],
            },
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    order2_submitted = ok(
        client.post(
            f"/api/v1/purchase-orders/{order2['id']}/submit",
            json={"version": order2["version"]},
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    ok(
        client.post(
            f"/api/v1/purchase-orders/{order2['id']}/review",
            json={"version": order2_submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    warehouse_id = ok(client.get("/api/v1/warehouses", headers=auth_headers(tokens, "V2C01")))[0][
        "id"
    ]
    movement = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "source_type": "purchase_order",
                "source_id": order2["id"],
                "items": [{"product_id": product_id, "quantity": "2"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    movement_submitted = ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/submit",
            json={"version": movement["version"]},
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    movement_executed = ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/execute",
            json={
                "version": movement_submitted["version"],
                "items": [{"product_id": product_id, "quantity": "2"}],
            },
            headers=auth_headers(tokens, "V2T01"),
        )
    )
    ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/review",
            json={"version": movement_executed["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    costs = _finance("stock_movement", movement["id"])
    assert [(r.record_type, str(r.amount), r.status) for r in costs] == [
        ("cost", "21.00", "approved")
    ]


def test_t18_sales_order_flow_generates_income_and_receivable(client, tokens) -> None:
    customer = ok(
        client.post(
            "/api/v1/customers",
            json={"code": f"CUS{uuid4().hex[:8]}", "name": "销售客户"},
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    product_id = _create_product(client, tokens)
    order = ok(
        client.post(
            "/api/v1/sales-orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_id": product_id, "quantity": "3", "unit_price": "20.00"}],
            },
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/submit",
            json={"version": order["version"]},
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    approved = ok(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/review",
            json={"version": submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    assert approved["status"] == "approved"

    records = _finance("sales_order", order["id"])
    assert [(r.record_type, str(r.amount), r.status) for r in records] == [
        ("receivable", "60.00", "approved"),
    ]

    # 重复审核不产生重复财务记录
    fail(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/review",
            json={"version": approved["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        ),
        409,
        3001,
    )
    assert len(_finance("sales_order", order["id"])) == 1

    # 出库审核通过后才确认收入并结转成本
    warehouse_id = ok(client.get("/api/v1/warehouses", headers=auth_headers(tokens, "V2C01")))[0][
        "id"
    ]
    stock_in = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "items": [{"product_id": product_id, "quantity": "5"}],
            },
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    ok(
        client.post(
            f"/api/v1/stock-movements/{stock_in['id']}/submit",
            json={"version": stock_in["version"]},
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    outbound = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "outbound",
                "warehouse_id": warehouse_id,
                "source_type": "sales_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "3"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    shipped = _flow_movement(client, tokens, outbound, "3")
    assert shipped["status"] == "approved"
    ship_records = _finance("stock_movement", outbound["id"])
    assert sorted((r.record_type, str(r.amount), r.status) for r in ship_records) == [
        ("cost", "30.00", "approved"),
        ("income", "60.00", "approved"),
    ]
    detail = ok(
        client.get(f"/api/v1/sales-orders/{order['id']}", headers=auth_headers(tokens, "V2B01"))
    )
    assert detail["fulfillment_status"] == "completed"


def _stock(client, tokens, product_id: int, warehouse_id: int) -> str:
    rows = ok(
        client.get(
            f"/api/v1/inventory?warehouse_id={warehouse_id}",
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    for row in rows:
        if row["product_id"] == product_id:
            return row["quantity"]
    return "0"


def _move(client, tokens, order: dict[str, Any], version: int) -> dict[str, Any]:
    return ok(
        client.post(
            f"/api/v1/stock-movements/{order['id']}/submit",
            json={"version": version},
            headers=auth_headers(tokens, "V2C01"),
        )
    )


def _adjustments(check_id: int) -> list[StockMovement]:
    db = SessionLocal()
    try:
        return list(
            db.scalars(
                select(StockMovement).where(
                    StockMovement.source_type == "stock_check",
                    StockMovement.source_id == check_id,
                )
            ).all()
        )
    finally:
        db.close()


def test_t19_inventory_movement_and_stock_check(client, tokens) -> None:
    product_id = _create_product(client, tokens)
    warehouses = ok(client.get("/api/v1/warehouses", headers=auth_headers(tokens, "V2C01")))
    warehouse_id = warehouses[0]["id"]

    # 入库：制单 → 提交 → 理货执行 → 仓库负责人审核过账
    inbound = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "items": [{"product_id": product_id, "quantity": "5"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    assert inbound["status"] == "draft"
    submitted = _move(client, tokens, inbound, inbound["version"])
    executed = ok(
        client.post(
            f"/api/v1/stock-movements/{inbound['id']}/execute",
            json={
                "version": submitted["version"],
                "items": [{"product_id": product_id, "quantity": "5"}],
            },
            headers=auth_headers(tokens, "V2T01"),
        )
    )
    assert executed["status"] == "pending_review"

    # 制单员无审核权限
    fail(
        client.post(
            f"/api/v1/stock-movements/{inbound['id']}/review",
            json={"version": executed["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2C01"),
        ),
        403,
        2001,
    )

    approved = ok(
        client.post(
            f"/api/v1/stock-movements/{inbound['id']}/review",
            json={"version": executed["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    assert approved["status"] == "approved"
    assert approved["items"][0]["after_quantity"] == "5.000"
    assert _stock(client, tokens, product_id, warehouse_id) == "5.000"

    # 出库超量：审核过账时拦截负库存
    outbound = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "outbound",
                "warehouse_id": warehouse_id,
                "items": [{"product_id": product_id, "quantity": "10"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    out_submitted = _move(client, tokens, outbound, outbound["version"])
    out_executed = ok(
        client.post(
            f"/api/v1/stock-movements/{outbound['id']}/execute",
            json={
                "version": out_submitted["version"],
                "items": [{"product_id": product_id, "quantity": "10"}],
            },
            headers=auth_headers(tokens, "V2T01"),
        )
    )
    fail(
        client.post(
            f"/api/v1/stock-movements/{outbound['id']}/review",
            json={"version": out_executed["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2W01"),
        ),
        409,
        3000,
    )


def _flow_movement(client, tokens, movement: dict[str, Any], quantity: str) -> dict[str, Any]:
    submitted = ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/submit",
            json={"version": movement["version"]},
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    executed = ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/execute",
            json={
                "version": submitted["version"],
                "items": [
                    {"product_id": movement["items"][0]["product_id"], "quantity": quantity}
                ],
            },
            headers=auth_headers(tokens, "V2T01"),
        )
    )
    return ok(
        client.post(
            f"/api/v1/stock-movements/{movement['id']}/review",
            json={"version": executed["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2W01"),
        )
    )


def test_t20_purchase_over_receipt_and_reversal(client, tokens) -> None:
    supplier = ok(
        client.post(
            "/api/v1/suppliers",
            json={"code": f"SUP{uuid4().hex[:8]}", "name": "履约供应商"},
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    product_id = _create_product(client, tokens)
    order = ok(
        client.post(
            "/api/v1/purchase-orders",
            json={
                "supplier_id": supplier["id"],
                "items": [{"product_id": product_id, "quantity": "5", "unit_price": "10.00"}],
            },
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/submit",
            json={"version": order["version"]},
            headers=auth_headers(tokens, "V2P01"),
        )
    )
    ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/review",
            json={"version": submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    warehouse_id = ok(client.get("/api/v1/warehouses", headers=auth_headers(tokens, "V2C01")))[0][
        "id"
    ]
    inbound = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "source_type": "purchase_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "5"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    approved = _flow_movement(client, tokens, inbound, "5")
    detail = ok(
        client.get(
            f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(tokens, "V2B01")
        )
    )
    assert detail["fulfillment_status"] == "completed"
    assert detail["items"][0]["remaining_quantity"] == "0.000"
    assert _stock(client, tokens, product_id, warehouse_id) == "5.000"

    # 超量入库被拦截
    fail(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "source_type": "purchase_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "1"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        ),
        409,
        3007,
    )

    # 红字冲销：库存回滚、履约回退、财务记录作废
    reversed_data = ok(
        client.post(
            f"/api/v1/stock-movements/{inbound['id']}/reverse",
            json={"version": approved["version"], "reason": "入库数量录错"},
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    assert reversed_data["movement"]["is_reversed"] is True
    assert reversed_data["reversal_no"]
    assert _stock(client, tokens, product_id, warehouse_id) == "0.000"
    detail2 = ok(
        client.get(
            f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(tokens, "V2B01")
        )
    )
    assert detail2["fulfillment_status"] == "none"
    assert all(record.status == "void" for record in _finance("stock_movement", inbound["id"]))

    # 冲销后订单可正常作废
    voided = ok(
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/void",
            json={"version": detail2["version"], "reason": "冲销后关闭"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    assert voided["status"] == "void"


def test_t21_sales_return_and_void_guard(client, tokens) -> None:
    customer = ok(
        client.post(
            "/api/v1/customers",
            json={"code": f"CUS{uuid4().hex[:8]}", "name": "退货客户"},
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    product_id = _create_product(client, tokens)
    warehouse_id = ok(client.get("/api/v1/warehouses", headers=auth_headers(tokens, "V2C01")))[0][
        "id"
    ]
    stock_in = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "items": [{"product_id": product_id, "quantity": "10"}],
            },
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    ok(
        client.post(
            f"/api/v1/stock-movements/{stock_in['id']}/submit",
            json={"version": stock_in["version"]},
            headers=auth_headers(tokens, "V2W01"),
        )
    )

    order = ok(
        client.post(
            "/api/v1/sales-orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_id": product_id, "quantity": "5", "unit_price": "20.00"}],
            },
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/submit",
            json={"version": order["version"]},
            headers=auth_headers(tokens, "V2S01"),
        )
    )
    approved = ok(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/review",
            json={"version": submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2B01"),
        )
    )
    outbound = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "outbound",
                "warehouse_id": warehouse_id,
                "source_type": "sales_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "5"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    _flow_movement(client, tokens, outbound, "5")

    # 已有有效出库单时禁止作废
    fail(
        client.post(
            f"/api/v1/sales-orders/{order['id']}/void",
            json={"version": approved["version"], "reason": "客户取消"},
            headers=auth_headers(tokens, "V2B01"),
        ),
        409,
        3009,
    )

    # 类型与来源不匹配
    fail(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "inbound",
                "warehouse_id": warehouse_id,
                "source_type": "sales_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "1"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        ),
        400,
        1000,
    )

    # 销售退货：入库并生成红字财务记录
    sales_return = ok(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "sales_return",
                "warehouse_id": warehouse_id,
                "source_type": "sales_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "2"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    returned = _flow_movement(client, tokens, sales_return, "2")
    assert returned["status"] == "approved"
    assert _stock(client, tokens, product_id, warehouse_id) == "7.000"
    return_records = _finance("stock_movement", sales_return["id"])
    assert sorted((r.record_type, str(r.amount), r.status) for r in return_records) == [
        ("cost_reversal", "20.00", "approved"),
        ("income_reversal", "40.00", "approved"),
    ]

    # 退货数量不得超过已出库数量
    fail(
        client.post(
            "/api/v1/stock-movements",
            json={
                "movement_type": "sales_return",
                "warehouse_id": warehouse_id,
                "source_type": "sales_order",
                "source_id": order["id"],
                "items": [{"product_id": product_id, "quantity": "4"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        ),
        409,
        3007,
    )
    assert _stock(client, tokens, product_id, warehouse_id) == "7.000"

    # 盘点：账面 7、实盘 8，审核通过生成盘盈调整并过账
    check = ok(
        client.post(
            "/api/v1/stock-checks",
            json={
                "warehouse_id": warehouse_id,
                "items": [{"product_id": product_id, "actual_quantity": "8"}],
            },
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    assert check["items"][0]["diff_quantity"] == "1.000"
    check_submitted = ok(
        client.post(
            f"/api/v1/stock-checks/{check['id']}/submit",
            json={"version": check["version"]},
            headers=auth_headers(tokens, "V2C01"),
        )
    )
    check_approved = ok(
        client.post(
            f"/api/v1/stock-checks/{check['id']}/review",
            json={"version": check_submitted["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2W01"),
        )
    )
    assert check_approved["status"] == "approved"
    assert _stock(client, tokens, product_id, warehouse_id) == "8.000"

    # T20 调整单可追溯
    adjustments = _adjustments(check["id"])
    assert [(row.movement_type, row.status) for row in adjustments] == [
        ("stocktake_in", "approved")
    ]


# 用随机业务日隔离重复运行产生的历史数据
BIZ_DAY = (date(2031, 1, 1) + timedelta(days=uuid4().int % 300)).isoformat()


def _clear_biz_day() -> None:
    """清理同一业务日的财务数据，避免历史运行残留影响断言。"""
    day = date.fromisoformat(BIZ_DAY)
    db = SessionLocal()
    try:
        db.execute(delete(FinanceRecord).where(FinanceRecord.record_date == day))
        db.execute(delete(CashFlow).where(CashFlow.flow_date == day))
        db.commit()
    finally:
        db.close()


def test_t21_finance_permissions_and_manual_records(client, tokens) -> None:
    _clear_biz_day()
    # 无财务权限
    fail(
        client.get("/api/v1/finance-records", headers=auth_headers(tokens, "V2K01")),
        403,
        2001,
    )

    # 出纳只能录资金流水
    fail(
        client.post(
            "/api/v1/finance-records",
            json={"record_type": "income", "amount": "10.00", "record_date": BIZ_DAY},
            headers=auth_headers(tokens, "V2CA1"),
        ),
        403,
        2001,
    )

    income = ok(
        client.post(
            "/api/v1/finance-records",
            json={"record_type": "income", "amount": "100.00", "record_date": BIZ_DAY},
            headers=auth_headers(tokens, "V2A01"),
        )
    )
    assert income["status"] == "pending_review"
    cost = ok(
        client.post(
            "/api/v1/finance-records",
            json={"record_type": "cost", "amount": "40.00", "record_date": BIZ_DAY},
            headers=auth_headers(tokens, "V2A01"),
        )
    )

    # 会计无审核权限
    fail(
        client.post(
            f"/api/v1/finance-records/{income['id']}/review",
            json={"version": income["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2A01"),
        ),
        403,
        2001,
    )
    for row in (income, cost):
        approved = ok(
            client.post(
                f"/api/v1/finance-records/{row['id']}/review",
                json={"version": row["version"], "decision": "approve"},
                headers=auth_headers(tokens, "V2F01"),
            )
        )
        assert approved["status"] == "approved"

    flow = ok(
        client.post(
            "/api/v1/cash-flows",
            json={
                "direction": "in",
                "amount": "500.00",
                "flow_date": BIZ_DAY,
                "payment_method": "bank_transfer",
            },
            headers=auth_headers(tokens, "V2CA1"),
        )
    )
    assert flow["status"] == "pending_review"
    flow_approved = ok(
        client.post(
            f"/api/v1/cash-flows/{flow['id']}/review",
            json={"version": flow["version"], "decision": "approve"},
            headers=auth_headers(tokens, "V2F01"),
        )
    )
    assert flow_approved["status"] == "approved"

    listed = ok(
        client.get(
            f"/api/v1/finance-records?start_date={BIZ_DAY}&end_date={BIZ_DAY}",
            headers=auth_headers(tokens, "V2F01"),
        )
    )
    assert listed["total"] == 2


def test_t22_metric_definitions(client, tokens) -> None:
    biz_day = date.fromisoformat(BIZ_DAY)
    db = SessionLocal()
    try:
        data = metric_service.finance_summary(db, biz_day, biz_day)
    finally:
        db.close()
    assert data["revenue"] == "100.00"
    assert data["cost"] == "40.00"
    assert data["gross_profit"] == "60.00"
    assert data["net_profit"] == "60.00"
    assert data["gross_margin"] == 60.0
    # 资金口径独立：余额不参与利润计算
    assert Decimal(data["cash_balance"]) >= Decimal("500.00")
    assert data["net_profit"] == "60.00"

    empty_day = date.fromisoformat("2030-01-01")
    db = SessionLocal()
    try:
        empty = metric_service.finance_summary(db, empty_day, empty_day)
    finally:
        db.close()
    assert empty["revenue"] == "0.00"
    assert empty["gross_margin"] is None
    assert empty["gross_margin_note"] == "分母为 0"


def _work_order_expenses(order_id: int) -> list[FinanceRecord]:
    db = SessionLocal()
    try:
        return list(
            db.scalars(
                select(FinanceRecord).where(
                    FinanceRecord.source_type == "work_order",
                    FinanceRecord.source_id == order_id,
                    FinanceRecord.record_type == "expense",
                )
            ).all()
        )
    finally:
        db.close()


def _employee_no(user_id: int) -> str:
    db = SessionLocal()
    try:
        employee_no = db.scalar(select(User.employee_no).where(User.id == user_id))
    finally:
        db.close()
    assert employee_no is not None
    return employee_no


def test_t23_expense_work_order_creates_finance_record(client, tokens) -> None:
    created = ok(create_order(client, tokens("F0001"), "expense_reimbursement"))
    order_id = created["id"]
    started = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/start",
            json={"version": created["version"]},
            headers=auth(tokens("F0001")),
        )
    )
    submitted = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/submit",
            json={"version": started["version"], "content": "报销材料已补齐"},
            headers=auth(tokens("F0001")),
        )
    )
    reviewed = ok(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": submitted["version"], "result": "approve"},
            headers=auth(tokens(_employee_no(created["reviewer_id"]))),
        )
    )
    assert reviewed["status"] == "completed"

    records = _work_order_expenses(order_id)
    assert len(records) == 1
    assert str(records[0].amount) == "120.50"
    assert records[0].status == "approved"

    # 重复审核不产生第二条费用
    fail(
        client.post(
            f"/api/v1/work_orders/{order_id}/review",
            json={"version": reviewed["version"], "result": "approve"},
            headers=auth(tokens(_employee_no(created["reviewer_id"]))),
        ),
        409,
        3001,
    )
    assert len(_work_order_expenses(order_id)) == 1
