import os

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin_or_inventory_manager,
)
from app.database import get_db
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.user import User
from app.schemas.sales_order import (
    SalesOrderCreate,
    SalesOrderDispatch,
    SalesOrderResponse,
    SalesOrderStatusResponse,
)
from app.services.email_service import send_email
from app.services.sales_order_service import (
    cancel_sales_order,
    confirm_sales_order,
    create_sales_order,
    deliver_sales_order,
    dispatch_sales_order,
    get_sales_order,
    list_sales_orders,
    pack_sales_order,
    pick_sales_order,
    update_sales_order,
)

router = APIRouter(prefix="/sales-orders", tags=["Sales Orders"])


def _schedule_customer_email(
    background_tasks: BackgroundTasks,
    db: Session,
    customer_id: int,
    subject: str,
    body: str,
) -> None:
    """Schedule an email without passing a database session to the task."""
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if customer and customer.email:
        background_tasks.add_task(
            send_email,
            customer.email,
            subject,
            body,
        )


def _schedule_low_stock_alerts(
    background_tasks: BackgroundTasks,
    db: Session,
    order,
) -> None:
    """Notify the configured recipient when dispatched stock is below reorder level."""
    alert_email = os.getenv("LOW_STOCK_ALERT_EMAIL")

    if not alert_email or not alert_email.strip():
        return

    for item in order.items:
        product = (
            db.query(Product)
            .filter(Product.id == item.product_id)
            .first()
        )

        inventory = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == item.product_id,
                Inventory.warehouse_id == order.warehouse_id,
            )
            .first()
        )

        if product is None or inventory is None:
            continue

        if inventory.quantity_available < product.reorder_level:
            background_tasks.add_task(
                send_email,
                alert_email.strip(),
                f"Low stock alert: {product.name}",
                (
                    f"Low stock detected after sales order "
                    f"{order.so_number} was dispatched.\n\n"
                    f"Product: {product.name}\n"
                    f"Warehouse ID: {order.warehouse_id}\n"
                    f"Quantity available: {inventory.quantity_available}\n"
                    f"Reorder level: {product.reorder_level}\n\n"
                    "Please review inventory and arrange replenishment."
                ),
            )


@router.post(
    "",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_order_endpoint(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return create_sales_order(db, payload, current_user)


@router.get("", response_model=list[SalesOrderResponse])
def list_sales_orders_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    order_status: str | None = Query(default=None, alias="status"),
    warehouse_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_sales_orders(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        order_status=order_status,
        warehouse_id=warehouse_id,
        customer_id=customer_id,
        search=search,
    )


@router.get("/{order_id}", response_model=SalesOrderResponse)
def get_sales_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_sales_order(db, order_id, current_user)


@router.put("/{order_id}", response_model=SalesOrderResponse)
def update_sales_order_endpoint(
    order_id: int,
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return update_sales_order(db, order_id, payload, current_user)


@router.put("/{order_id}/confirm", response_model=SalesOrderResponse)
def confirm_sales_order_endpoint(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    order = confirm_sales_order(db, order_id, current_user)

    _schedule_customer_email(
        background_tasks=background_tasks,
        db=db,
        customer_id=order.customer_id,
        subject=f"Sales order {order.so_number} confirmed",
        body=(
            f"Your sales order {order.so_number} has been confirmed.\n\n"
            f"Order total: {order.grand_total}\n"
            f"Status: {order.status}\n\n"
            "Thank you for your order."
        ),
    )

    return order


@router.put("/{order_id}/cancel", response_model=SalesOrderResponse)
def cancel_sales_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return cancel_sales_order(db, order_id, current_user)


@router.put("/{order_id}/pick", response_model=SalesOrderStatusResponse)
def pick_sales_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return pick_sales_order(db, order_id, current_user)


@router.put("/{order_id}/pack", response_model=SalesOrderStatusResponse)
def pack_sales_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return pack_sales_order(db, order_id, current_user)


@router.put("/{order_id}/dispatch", response_model=SalesOrderResponse)
def dispatch_sales_order_endpoint(
    order_id: int,
    payload: SalesOrderDispatch,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = dispatch_sales_order(
        db=db,
        order_id=order_id,
        courier_name=payload.courier_name,
        tracking_number=payload.tracking_number,
        current_user=current_user,
    )

    _schedule_customer_email(
        background_tasks=background_tasks,
        db=db,
        customer_id=order.customer_id,
        subject=f"Sales order {order.so_number} dispatched",
        body=(
            f"Your sales order {order.so_number} has been dispatched.\n\n"
            f"Courier: {order.courier_name}\n"
            f"Tracking number: {order.tracking_number}\n"
            f"Dispatch time: {order.dispatched_at}\n\n"
            "Please use the tracking number to follow your delivery."
        ),
    )

    _schedule_low_stock_alerts(
        background_tasks=background_tasks,
        db=db,
        order=order,
    )

    return order


@router.put("/{order_id}/deliver", response_model=SalesOrderStatusResponse)
def deliver_sales_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return deliver_sales_order(db, order_id, current_user)