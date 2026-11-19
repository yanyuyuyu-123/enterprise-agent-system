from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.schemas.business import (
    CashFlowCreate,
    CustomerCreate,
    CustomerUpdate,
    FinanceRecordCreate,
    MovementExecute,
    MovementReverse,
    OrderReview,
    OrderSubmit,
    OrderVoid,
    ProductCreate,
    ProductUpdate,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    SalesOrderCreate,
    SalesOrderUpdate,
    StockCheckCreate,
    StockMovementCreate,
    SupplierCreate,
    SupplierUpdate,
)
from app.services import (
    finance_service,
    inventory_service,
    partner_service,
    product_service,
    purchase_service,
    sales_service,
)
from app.services.permission_service import Principal

router = APIRouter(tags=["business"])


@router.get("/suppliers")
def list_suppliers(
    request: Request,
    keyword: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = partner_service.list_suppliers(
        db, principal, keyword=keyword, status=status, page=page, page_size=page_size
    )
    return ok(request, data)


@router.post("/suppliers")
def create_supplier(
    payload: SupplierCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.create_supplier(db, principal, payload), status_code=201)


@router.get("/suppliers/{supplier_id}")
def get_supplier(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.get_supplier(db, principal, supplier_id))


@router.put("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.update_supplier(db, principal, supplier_id, payload))


@router.get("/customers")
def list_customers(
    request: Request,
    keyword: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = partner_service.list_customers(
        db, principal, keyword=keyword, status=status, page=page, page_size=page_size
    )
    return ok(request, data)


@router.post("/customers")
def create_customer(
    payload: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.create_customer(db, principal, payload), status_code=201)


@router.get("/customers/{customer_id}")
def get_customer(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.get_customer(db, principal, customer_id))


@router.put("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, partner_service.update_customer(db, principal, customer_id, payload))


@router.get("/products")
def list_products(
    request: Request,
    keyword: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = product_service.list_products(
        db,
        principal,
        keyword=keyword,
        category=category,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/products")
def create_product(
    payload: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, product_service.create_product(db, principal, payload), status_code=201)


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, product_service.get_product(db, principal, product_id))


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, product_service.update_product(db, principal, product_id, payload))


@router.get("/purchase-orders")
def list_purchase_orders(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    supplier_id: int | None = None,
    fulfillment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = purchase_service.list_purchase_orders(
        db,
        principal,
        status=status,
        keyword=keyword,
        supplier_id=supplier_id,
        fulfillment_status=fulfillment_status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/purchase-orders")
def create_purchase_order(
    payload: PurchaseOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(
        request, purchase_service.create_purchase_order(db, principal, payload), status_code=201
    )


@router.get("/purchase-orders/{order_id}")
def get_purchase_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, purchase_service.get_purchase_order(db, principal, order_id))


@router.put("/purchase-orders/{order_id}")
def update_purchase_order(
    order_id: int,
    payload: PurchaseOrderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, purchase_service.update_purchase_order(db, principal, order_id, payload))


@router.post("/purchase-orders/{order_id}/submit")
def submit_purchase_order(
    order_id: int,
    payload: OrderSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, purchase_service.submit_purchase_order(db, principal, order_id, payload))


@router.post("/purchase-orders/{order_id}/review")
def review_purchase_order(
    order_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, purchase_service.review_purchase_order(db, principal, order_id, payload))


@router.post("/purchase-orders/{order_id}/void")
def void_purchase_order(
    order_id: int,
    payload: OrderVoid,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, purchase_service.void_purchase_order(db, principal, order_id, payload))


@router.get("/sales-orders")
def list_sales_orders(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    customer_id: int | None = None,
    fulfillment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = sales_service.list_sales_orders(
        db,
        principal,
        status=status,
        keyword=keyword,
        customer_id=customer_id,
        fulfillment_status=fulfillment_status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/sales-orders")
def create_sales_order(
    payload: SalesOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.create_sales_order(db, principal, payload), status_code=201)


@router.get("/sales-orders/{order_id}")
def get_sales_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.get_sales_order(db, principal, order_id))


@router.put("/sales-orders/{order_id}")
def update_sales_order(
    order_id: int,
    payload: SalesOrderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.update_sales_order(db, principal, order_id, payload))


@router.post("/sales-orders/{order_id}/submit")
def submit_sales_order(
    order_id: int,
    payload: OrderSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.submit_sales_order(db, principal, order_id, payload))


@router.post("/sales-orders/{order_id}/review")
def review_sales_order(
    order_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.review_sales_order(db, principal, order_id, payload))


@router.post("/sales-orders/{order_id}/void")
def void_sales_order(
    order_id: int,
    payload: OrderVoid,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, sales_service.void_sales_order(db, principal, order_id, payload))


@router.get("/warehouses")
def list_warehouses(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.list_warehouses(db, principal))


@router.get("/inventory")
def list_inventory(
    request: Request,
    warehouse_id: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(
        request,
        inventory_service.list_inventory(db, principal, warehouse_id=warehouse_id, keyword=keyword),
    )


@router.get("/stock-movements")
def list_stock_movements(
    request: Request,
    status: str | None = None,
    warehouse_id: int | None = None,
    keyword: str | None = None,
    movement_type: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = inventory_service.list_movements(
        db,
        principal,
        status=status,
        warehouse_id=warehouse_id,
        keyword=keyword,
        movement_type=movement_type,
        source_type=source_type,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/stock-movements")
def create_stock_movement(
    payload: StockMovementCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.create_movement(db, principal, payload), status_code=201)


@router.get("/stock-movements/{movement_id}")
def get_stock_movement(
    movement_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.get_movement(db, principal, movement_id))


@router.post("/stock-movements/{movement_id}/submit")
def submit_stock_movement(
    movement_id: int,
    payload: OrderSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.submit_movement(db, principal, movement_id, payload))


@router.post("/stock-movements/{movement_id}/execute")
def execute_stock_movement(
    movement_id: int,
    payload: MovementExecute,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.execute_movement(db, principal, movement_id, payload))


@router.post("/stock-movements/{movement_id}/review")
def review_stock_movement(
    movement_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.review_movement(db, principal, movement_id, payload))


@router.post("/stock-movements/{movement_id}/reverse")
def reverse_stock_movement(
    movement_id: int,
    payload: MovementReverse,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.reverse_movement(db, principal, movement_id, payload))


@router.get("/stock-checks")
def list_stock_checks(
    request: Request,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = inventory_service.list_checks(
        db, principal, status=status, page=page, page_size=page_size
    )
    return ok(request, data)


@router.post("/stock-checks")
def create_stock_check(
    payload: StockCheckCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.create_check(db, principal, payload), status_code=201)


@router.get("/stock-checks/{check_id}")
def get_stock_check(
    check_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.get_check(db, principal, check_id))


@router.post("/stock-checks/{check_id}/submit")
def submit_stock_check(
    check_id: int,
    payload: OrderSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.submit_check(db, principal, check_id, payload))


@router.post("/stock-checks/{check_id}/review")
def review_stock_check(
    check_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, inventory_service.review_check(db, principal, check_id, payload))


@router.get("/finance-records")
def list_finance_records(
    request: Request,
    record_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = finance_service.list_records(
        db,
        principal,
        record_type=record_type,
        status=status,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/finance-records")
def create_finance_record(
    payload: FinanceRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.create_record(db, principal, payload), status_code=201)


@router.get("/finance-records/{record_id}")
def get_finance_record(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.get_record(db, principal, record_id))


@router.post("/finance-records/{record_id}/review")
def review_finance_record(
    record_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.review_record(db, principal, record_id, payload))


@router.post("/finance-records/{record_id}/void")
def void_finance_record(
    record_id: int,
    payload: OrderVoid,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.void_record(db, principal, record_id, payload))


@router.get("/cash-flows")
def list_cash_flows(
    request: Request,
    direction: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = finance_service.list_cash_flows(
        db,
        principal,
        direction=direction,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(request, data)


@router.post("/cash-flows")
def create_cash_flow(
    payload: CashFlowCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.create_cash_flow(db, principal, payload), status_code=201)


@router.get("/cash-flows/{flow_id}")
def get_cash_flow(
    flow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.get_cash_flow(db, principal, flow_id))


@router.post("/cash-flows/{flow_id}/review")
def review_cash_flow(
    flow_id: int,
    payload: OrderReview,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.review_cash_flow(db, principal, flow_id, payload))


@router.post("/cash-flows/{flow_id}/void")
def void_cash_flow(
    flow_id: int,
    payload: OrderVoid,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, finance_service.void_cash_flow(db, principal, flow_id, payload))
