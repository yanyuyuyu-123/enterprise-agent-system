"""业务单据工具：单据查询、待办、库存、应收应付，以及草稿/提交/审核写操作。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.org import User
from app.schemas.business import (
    OrderItemIn,
    OrderReview,
    OrderSubmit,
    OrderVoid,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    SalesOrderCreate,
    SalesOrderUpdate,
    StockMovementCreate,
)
from app.services import finance_service, inventory_service, purchase_service, sales_service
from app.services.permission_service import Principal, require_permission


def _ok(data: Any, message: str = "ok", source: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "source": source or {"type": "business"},
        "message": message,
    }


def _find_order(db: Session, principal: Principal, order_no: str) -> tuple[str, dict[str, Any]]:
    no = order_no.strip().upper()
    if no.startswith("PO"):
        data = purchase_service.list_purchase_orders(
            db, principal, keyword=no, page=1, page_size=5
        )
        order_type = "purchase"
    elif no.startswith("SO"):
        data = sales_service.list_sales_orders(db, principal, keyword=no, page=1, page_size=5)
        order_type = "sales"
    elif no.startswith("SM"):
        data = inventory_service.list_movements(
            db, principal, keyword=no, page=1, page_size=5
        )
        order_type = "movement"
    else:
        raise AppError(3003, "单号格式无法识别，支持 PO/SO/SM 开头", 404)
    matched = None
    if order_type == "movement":
        matched = next(
            (item for item in data["items"] if item.get("movement_no") == no), None
        )
    else:
        matched = next((item for item in data["items"] if item.get("order_no") == no), None)
    if matched is None:
        raise AppError(3003, "单据不存在或无权查看", 404)
    return order_type, matched


def tool_purchase_order_detail(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "purchase_order", "read")
    order_type, data = _find_order(db, principal, str(args["order_no"]))
    if order_type != "purchase":
        raise AppError(1000, "该单号不是采购单", 400)
    return _ok(data)


def tool_sales_order_detail(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "sales_order", "read")
    order_type, data = _find_order(db, principal, str(args["order_no"]))
    if order_type != "sales":
        raise AppError(1000, "该单号不是销售单", 400)
    return _ok(data)


def tool_movement_detail(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "inventory", "read")
    order_type, data = _find_order(db, principal, str(args["order_no"]))
    if order_type != "movement":
        raise AppError(1000, "该单号不是出入库单", 400)
    return _ok(data)


def tool_stock_by_product(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "inventory", "read")
    warehouse_id = args.get("warehouse_id")
    rows = inventory_service.list_inventory(
        db,
        principal,
        warehouse_id=int(warehouse_id) if warehouse_id is not None else None,
        keyword=args.get("keyword"),
    )
    total = sum(float(row["quantity"]) for row in rows)
    return _ok(
        {
            "items": rows,
            "total": len(rows),
            "quantity_total": round(total, 3),
            "keyword": args.get("keyword"),
        }
    )


def tool_receivable_payable(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    record_type = args.get("record_type")
    start = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    data = finance_service.receivable_payable_detail(
        db, principal, record_type=record_type, start_date=start, end_date=end
    )
    return _ok(data)


def _safe_list(fn, *args, **kwargs) -> list[dict[str, Any]]:
    try:
        return fn(*args, **kwargs)["items"]
    except AppError:
        return []


def tool_pending_tasks(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "work_order", "read")
    tasks: list[dict[str, Any]] = []
    for item in _safe_list(
        purchase_service.list_purchase_orders, db, principal, status="pending_review"
    ):
        tasks.append(
            {
                "kind": "采购单待审核",
                "doc_no": item["order_no"],
                "status": item["status"],
                "amount": item.get("total_amount"),
                "created_by": item.get("purchaser_name"),
                "can_review": item.get("created_by") != principal.user_id,
            }
        )
    for item in _safe_list(
        sales_service.list_sales_orders, db, principal, status="pending_review"
    ):
        tasks.append(
            {
                "kind": "销售单待审核",
                "doc_no": item["order_no"],
                "status": item["status"],
                "amount": item.get("total_amount"),
                "created_by": item.get("salesperson_name"),
                "can_review": item.get("created_by") != principal.user_id,
            }
        )
    for item in _safe_list(
        inventory_service.list_movements, db, principal, status="pending_execute"
    ):
        tasks.append(
            {
                "kind": "出入库待执行",
                "doc_no": item["movement_no"],
                "status": item["status"],
                "created_by": item.get("created_by"),
            }
        )
    for item in _safe_list(
        inventory_service.list_movements, db, principal, status="pending_review"
    ):
        tasks.append(
            {
                "kind": "出入库待审核",
                "doc_no": item["movement_no"],
                "status": item["status"],
                "can_review": item.get("created_by") != principal.user_id,
            }
        )
    mine = db.get(User, principal.user_id)
    return _ok(
        {
            "items": tasks[:50],
            "total": len(tasks),
            "user": mine.name if mine else principal.name,
        }
    )


def _items(args: dict[str, Any]) -> list[OrderItemIn]:
    items = []
    for raw in args.get("items") or []:
        quantity = raw.get("quantity")
        unit_price = raw.get("unit_price")
        if raw.get("product_id") is None or quantity is None or unit_price is None:
            raise AppError(1000, "明细需要 product_id、quantity、unit_price", 400)
        items.append(
            OrderItemIn(
                product_id=int(raw["product_id"]),
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    if not items:
        raise AppError(1000, "至少需要一条明细", 400)
    return items


def tool_create_purchase_draft(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    payload = PurchaseOrderCreate(
        supplier_id=int(args["supplier_id"]),
        order_date=date.fromisoformat(args["order_date"]) if args.get("order_date") else None,
        expected_date=date.fromisoformat(args["expected_date"])
        if args.get("expected_date")
        else None,
        remark=args.get("remark"),
        items=_items(args),
    )
    data = purchase_service.create_purchase_order(db, principal, payload)
    return _ok(data, message=f"采购草稿 {data['order_no']} 已创建")


def tool_create_sales_draft(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    payload = SalesOrderCreate(
        customer_id=int(args["customer_id"]),
        order_date=date.fromisoformat(args["order_date"]) if args.get("order_date") else None,
        remark=args.get("remark"),
        items=_items(args),
    )
    data = sales_service.create_sales_order(db, principal, payload)
    return _ok(data, message=f"销售草稿 {data['order_no']} 已创建")


def tool_create_movement_draft(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    source_type = args.get("source_type") or "manual"
    source_id = args.get("source_id")
    movement_type = args.get("movement_type")
    warehouse_id = args.get("warehouse_id")

    if source_type in ("purchase_order", "sales_order") and source_id is not None:
        order_type = "purchase" if source_type == "purchase_order" else "sales"
        if order_type == "purchase":
            order = purchase_service.get_purchase_order(db, principal, int(source_id))
        else:
            order = sales_service.get_sales_order(db, principal, int(source_id))
        if order["status"] != "approved":
            raise AppError(3001, "来源订单尚未审核通过", 409)
        movement_type = movement_type or (
            "inbound" if source_type == "purchase_order" else "outbound"
        )
        if not args.get("items"):
            items = [
                {
                    "product_id": item["product_id"],
                    "quantity": item["remaining_quantity"],
                }
                for item in order["items"]
                if float(item["remaining_quantity"]) > 0
            ]
            if not items:
                raise AppError(3001, "来源订单已全部执行", 409)
            args = {**args, "items": items}

    if warehouse_id is None:
        warehouses = inventory_service.list_warehouses(db, principal)
        if len(warehouses) != 1:
            raise AppError(1000, "请指定 warehouse_id（可用仓库不止一个）", 400)
        warehouse_id = warehouses[0]["id"]

    payload = StockMovementCreate(
        movement_type=movement_type,
        warehouse_id=int(warehouse_id),
        source_type=source_type,
        source_id=int(source_id) if source_id is not None else None,
        remark=args.get("remark"),
        items=[
            {"product_id": int(item["product_id"]), "quantity": item["quantity"]}
            for item in args.get("items") or []
        ],
    )
    data = inventory_service.create_movement(db, principal, payload)
    return _ok(data, message=f"出入库草稿 {data['movement_no']} 已创建")


def _as_date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def tool_purchase_order_list(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "purchase_order", "read")
    data = purchase_service.list_purchase_orders(
        db,
        principal,
        status=args.get("status"),
        keyword=args.get("keyword"),
        supplier_id=args.get("supplier_id"),
        fulfillment_status=args.get("fulfillment_status"),
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        page=int(args.get("page") or 1),
        page_size=min(int(args.get("page_size") or 20), 100),
    )
    return _ok(data)


def tool_sales_order_list(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "sales_order", "read")
    data = sales_service.list_sales_orders(
        db,
        principal,
        status=args.get("status"),
        keyword=args.get("keyword"),
        customer_id=args.get("customer_id"),
        fulfillment_status=args.get("fulfillment_status"),
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        page=int(args.get("page") or 1),
        page_size=min(int(args.get("page_size") or 20), 100),
    )
    return _ok(data)


def tool_movement_list(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    require_permission(principal, "inventory", "read")
    data = inventory_service.list_movements(
        db,
        principal,
        status=args.get("status"),
        warehouse_id=args.get("warehouse_id"),
        keyword=args.get("keyword"),
        movement_type=args.get("movement_type"),
        source_type=args.get("source_type"),
        source_id=args.get("source_id"),
        start_date=_as_date(args.get("start_date")),
        end_date=_as_date(args.get("end_date")),
        page=int(args.get("page") or 1),
        page_size=min(int(args.get("page_size") or 20), 100),
    )
    return _ok(data)


def _remaining_lines(order: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "product_id": item["product_id"],
            "product_name": item.get("product_name"),
            "quantity": item["quantity"],
            "executed_quantity": item.get("executed_quantity"),
            "remaining_quantity": item.get("remaining_quantity"),
        }
        for item in order.get("items") or []
        if float(item.get("remaining_quantity") or 0) > 0
    ]


def tool_fulfillment_reminders(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order_type = args.get("order_type") or "all"
    limit = min(int(args.get("limit") or 20), 50)
    items: list[dict[str, Any]] = []

    if order_type in ("all", "purchase"):
        for order in _safe_list(
            purchase_service.list_purchase_orders,
            db,
            principal,
            status="approved",
            page_size=100,
        ):
            if order["fulfillment_status"] == "completed":
                continue
            items.append(
                {
                    "order_type": "purchase",
                    "order_no": order["order_no"],
                    "counterparty": order.get("supplier_name"),
                    "fulfillment_status": order["fulfillment_status"],
                    "total_amount": order.get("total_amount"),
                    "lines": _remaining_lines(order),
                }
            )
    if order_type in ("all", "sales"):
        for order in _safe_list(
            sales_service.list_sales_orders,
            db,
            principal,
            status="approved",
            page_size=100,
        ):
            if order["fulfillment_status"] == "completed":
                continue
            items.append(
                {
                    "order_type": "sales",
                    "order_no": order["order_no"],
                    "counterparty": order.get("customer_name"),
                    "fulfillment_status": order["fulfillment_status"],
                    "total_amount": order.get("total_amount"),
                    "lines": _remaining_lines(order),
                }
            )
    return _ok({"items": items[:limit], "total": len(items)})


def tool_update_order(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order_type = args.get("order_type")
    order_id = int(args["order_id"])
    version = int(args.get("version") or 0)
    items = args.get("items")
    remark = args.get("remark")
    if not items and remark is None:
        raise AppError(1000, "需要提供新的明细或备注", 400)

    if order_type == "purchase":
        payload = PurchaseOrderUpdate(
            version=version,
            remark=remark,
            items=_items(args) if items else None,
        )
        data = purchase_service.update_purchase_order(db, principal, order_id, payload)
    elif order_type == "sales":
        payload = SalesOrderUpdate(
            version=version,
            remark=remark,
            items=_items(args) if items else None,
        )
        data = sales_service.update_sales_order(db, principal, order_id, payload)
    else:
        raise AppError(1000, "order_type 仅支持 purchase/sales", 400)
    return _ok(data, message="单据已更新")


def tool_cancel_order(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order_type = args.get("order_type")
    order_id = int(args["order_id"])
    payload = OrderVoid(
        version=int(args.get("version") or 0),
        reason=str(args.get("reason") or "用户通过智能助手取消"),
    )
    if order_type == "purchase":
        data = purchase_service.void_purchase_order(db, principal, order_id, payload)
    elif order_type == "sales":
        data = sales_service.void_sales_order(db, principal, order_id, payload)
    else:
        raise AppError(1000, "order_type 仅支持 purchase/sales", 400)
    return _ok(data, message="单据已作废")


def tool_submit_order(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order_type = args["order_type"]
    order_id = int(args["order_id"])
    payload = OrderSubmit(version=int(args.get("version") or 0))
    if order_type == "purchase":
        data = purchase_service.submit_purchase_order(db, principal, order_id, payload)
    elif order_type == "sales":
        data = sales_service.submit_sales_order(db, principal, order_id, payload)
    elif order_type == "movement":
        data = inventory_service.submit_movement(db, principal, order_id, payload)
    else:
        raise AppError(1000, "order_type 仅支持 purchase/sales/movement", 400)
    return _ok(data, message="单据已提交")


def tool_review_order(
    db: Session, principal: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    order_type = args["order_type"]
    order_id = int(args["order_id"])
    payload = OrderReview(
        version=int(args.get("version") or 0),
        decision=args.get("decision") or "approve",
        comment=args.get("comment"),
    )
    if payload.decision not in ("approve", "reject"):
        raise AppError(1000, "decision 仅支持 approve/reject", 400)
    if order_type == "purchase":
        data = purchase_service.review_purchase_order(db, principal, order_id, payload)
    elif order_type == "sales":
        data = sales_service.review_sales_order(db, principal, order_id, payload)
    elif order_type == "movement":
        data = inventory_service.review_movement(db, principal, order_id, payload)
    else:
        raise AppError(1000, "order_type 仅支持 purchase/sales/movement", 400)
    verb = "审核通过" if payload.decision == "approve" else "已驳回"
    return _ok(data, message=f"单据{verb}")
