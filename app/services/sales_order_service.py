from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.stock_movement import StockMovement
from app.models.warehouse import Warehouse
from app.models.user import User


GST_RATE = Decimal("0.18")
MONEY = Decimal("0.01")

OPEN_ORDER_STATUSES = {
    "Confirmed",
    "Picked",
    "Packed",
    "Dispatched",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _order_snapshot(order: SalesOrder) -> dict:
    return {
        "so_number": order.so_number,
        "customer_id": order.customer_id,
        "warehouse_id": order.warehouse_id,
        "subtotal": str(order.subtotal),
        "tax_amount": str(order.tax_amount),
        "grand_total": str(order.grand_total),
        "status": order.status,
        "courier_name": order.courier_name,
        "tracking_number": order.tracking_number,
        "dispatched_at": (
            order.dispatched_at.isoformat() if order.dispatched_at else None
        ),
        "delivered_at": (
            order.delivered_at.isoformat() if order.delivered_at else None
        ),
    }


def _write_audit(
    db: Session,
    user_id: int,
    action: str,
    order: SalesOrder,
    old_value: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type="SalesOrder",
            entity_id=order.id,
            old_value=old_value,
            new_value=_order_snapshot(order),
            timestamp=datetime.utcnow(),
        )
    )


def _get_order(db: Session, order_id: int) -> SalesOrder:
    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found",
        )
    return order


def _require_manager(current_user: User) -> None:
    if current_user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inventory Manager access required",
        )


def _require_warehouse_access(
    order: SalesOrder,
    current_user: User,
) -> None:
    if current_user.role == "Admin":
        return

    if current_user.role != "Warehouse Staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or assigned Warehouse Staff access required",
        )

    if current_user.assigned_warehouse_id != order.warehouse_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this order's warehouse",
        )


def _check_credit_limit(
    db: Session,
    customer: Customer,
    order: SalesOrder,
) -> None:
    open_total = (
        db.query(func.coalesce(func.sum(SalesOrder.grand_total), 0))
        .filter(
            SalesOrder.customer_id == customer.id,
            SalesOrder.id != order.id,
            SalesOrder.status.in_(OPEN_ORDER_STATUSES),
        )
        .scalar()
    )

    total_after_confirmation = Decimal(str(open_total)) + order.grand_total

    if total_after_confirmation > customer.credit_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Customer credit limit exceeded. "
                f"Open orders plus this order would total "
                f"{total_after_confirmation}, exceeding "
                f"the credit limit of {customer.credit_limit}."
            ),
        )


def create_sales_order(
    db: Session,
    payload,
    current_user: User,
) -> SalesOrder:
    _require_manager(current_user)

    customer = (
        db.query(Customer)
        .filter(Customer.id == payload.customer_id)
        .with_for_update()
        .first()
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inactive customers cannot place sales orders",
        )

    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == payload.warehouse_id)
        .first()
    )
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )
    if not warehouse.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create a sales order for an inactive warehouse",
        )

    requested_product_ids = [item.product_id for item in payload.items]
    if len(requested_product_ids) != len(set(requested_product_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each product may appear only once in a sales order",
        )

    subtotal = Decimal("0.00")
    order_items = []

    for requested_item in payload.items:
        product = (
            db.query(Product)
            .filter(Product.id == requested_item.product_id)
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {requested_item.product_id} not found",
            )
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product {product.name} is inactive",
            )

        unit_price = Decimal(str(product.selling_price))
        line_total = _money(unit_price * requested_item.quantity)
        subtotal += line_total

        order_items.append(
            {
                "product_id": product.id,
                "quantity": requested_item.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    subtotal = _money(subtotal)
    tax_amount = _money(subtotal * GST_RATE)
    grand_total = _money(subtotal + tax_amount)

    try:
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"SO-{today}-"

        last_order = (
            db.query(SalesOrder)
            .filter(SalesOrder.so_number.like(f"{prefix}%"))
            .order_by(SalesOrder.so_number.desc())
            .with_for_update()
            .first()
        )

        next_number = 1
        if last_order:
            try:
                next_number = int(last_order.so_number.rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                next_number = 1

        order = SalesOrder(
            so_number=f"{prefix}{next_number:04d}",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            subtotal=subtotal,
            tax_amount=tax_amount,
            grand_total=grand_total,
            status="Draft",
            created_by=current_user.id,
        )

        db.add(order)
        db.flush()

        for item in order_items:
            db.add(
                SalesOrderItem(
                    sales_order_id=order.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    line_total=item["line_total"],
                    created_by=current_user.id,
                )
            )

        db.flush()
        _write_audit(db, current_user.id, "CREATE", order)
        db.commit()
        db.refresh(order)
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def list_sales_orders(
    db: Session,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
    order_status: str | None = None,
    warehouse_id: int | None = None,
    customer_id: int | None = None,
    search: str | None = None,
) -> list[SalesOrder]:
    query = db.query(SalesOrder)

    if current_user.role == "Warehouse Staff":
        query = query.filter(
            SalesOrder.warehouse_id == current_user.assigned_warehouse_id
        )
    elif current_user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    if order_status:
        query = query.filter(SalesOrder.status == order_status)
    if warehouse_id is not None:
        query = query.filter(SalesOrder.warehouse_id == warehouse_id)
    if customer_id is not None:
        query = query.filter(SalesOrder.customer_id == customer_id)
    if search:
        query = query.filter(SalesOrder.so_number.ilike(f"%{search.strip()}%"))

    return (
        query.order_by(SalesOrder.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    order = _get_order(db, order_id)

    if current_user.role == "Warehouse Staff":
        _require_warehouse_access(order, current_user)
    elif current_user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return order


def update_sales_order(
    db: Session,
    order_id: int,
    payload,
    current_user: User,
) -> SalesOrder:
    _require_manager(current_user)
    order = _get_order(db, order_id)

    if order.status != "Draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Draft sales orders can be updated",
        )

    changes = payload.model_dump(exclude_unset=True)

    customer_id = changes.get("customer_id", order.customer_id)
    warehouse_id = changes.get("warehouse_id", order.warehouse_id)
    requested_items = changes.get("items")

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()

    if customer is None or not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer does not exist or is inactive",
        )
    if warehouse is None or not warehouse.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse does not exist or is inactive",
        )

    old_value = _order_snapshot(order)

    try:
        order.customer_id = customer_id
        order.warehouse_id = warehouse_id

        if requested_items is not None:
            product_ids = [item.product_id for item in requested_items]
            if not product_ids or len(product_ids) != len(set(product_ids)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Items must be non-empty and contain unique product IDs",
                )

            for old_item in list(order.items):
                db.delete(old_item)
            db.flush()

            subtotal = Decimal("0.00")

            for requested_item in requested_items:
                product = (
                    db.query(Product)
                    .filter(Product.id == requested_item.product_id)
                    .first()
                )
                if product is None or not product.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Product {requested_item.product_id} does not exist or is inactive",
                    )

                unit_price = Decimal(str(product.selling_price))
                line_total = _money(unit_price * requested_item.quantity)
                subtotal += line_total

                db.add(
                    SalesOrderItem(
                        sales_order_id=order.id,
                        product_id=product.id,
                        quantity=requested_item.quantity,
                        unit_price=unit_price,
                        line_total=line_total,
                        created_by=current_user.id,
                    )
                )

            order.subtotal = _money(subtotal)
            order.tax_amount = _money(order.subtotal * GST_RATE)
            order.grand_total = _money(order.subtotal + order.tax_amount)

        db.flush()
        _write_audit(
            db,
            current_user.id,
            "UPDATE",
            order,
            old_value=old_value,
        )
        db.commit()
        db.refresh(order)
        return order

    except Exception:
        db.rollback()
        raise


def confirm_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    _require_manager(current_user)
    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found",
        )
    if order.status != "Draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Draft sales orders can be confirmed",
        )
    if not order.items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot confirm an order without items",
        )

    customer = (
        db.query(Customer)
        .filter(Customer.id == order.customer_id)
        .with_for_update()
        .first()
    )
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == order.warehouse_id)
        .first()
    )

    if customer is None or not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer is missing or inactive",
        )
    if warehouse is None or not warehouse.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse is missing or inactive",
        )

    old_value = _order_snapshot(order)

    try:
        _check_credit_limit(db, customer, order)

        locked_inventory = {}
        for item in order.items:
            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == order.warehouse_id,
                )
                .with_for_update()
                .first()
            )

            if inventory is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No inventory record for product {item.product_id} in this warehouse",
                )

            if inventory.quantity_on_hand - inventory.quantity_reserved < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient available stock for product {item.product_id}",
                )

            locked_inventory[item.product_id] = inventory

        for item in order.items:
            inventory = locked_inventory[item.product_id]
            inventory.quantity_reserved += item.quantity
            inventory.updated_at = datetime.utcnow()

        order.status = "Confirmed"
        db.flush()
        _write_audit(
            db,
            current_user.id,
            "CONFIRM",
            order,
            old_value=old_value,
        )
        db.commit()
        db.refresh(order)
        return order

    except Exception:
        db.rollback()
        raise


def cancel_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    _require_manager(current_user)

    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found",
        )

    if order.status not in {"Draft", "Confirmed", "Picked", "Packed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Draft, Confirmed, Picked, or Packed orders can be cancelled",
        )

    old_value = _order_snapshot(order)

    try:
        if order.status in {"Confirmed", "Picked", "Packed"}:
            for item in order.items:
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.product_id == item.product_id,
                        Inventory.warehouse_id == order.warehouse_id,
                    )
                    .with_for_update()
                    .first()
                )

                if inventory is None or inventory.quantity_reserved < item.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Reserved inventory is inconsistent; cancellation aborted",
                    )

                inventory.quantity_reserved -= item.quantity
                inventory.updated_at = datetime.utcnow()

        order.status = "Cancelled"
        db.flush()
        _write_audit(
            db,
            current_user.id,
            "CANCEL",
            order,
            old_value=old_value,
        )
        db.commit()
        db.refresh(order)
        return order

    except Exception:
        db.rollback()
        raise


def pick_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    order = _get_order(db, order_id)
    _require_warehouse_access(order, current_user)

    if order.status != "Confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Confirmed orders can be picked",
        )

    old_value = _order_snapshot(order)
    order.status = "Picked"

    try:
        _write_audit(db, current_user.id, "PICK", order, old_value)
        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise


def pack_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    order = _get_order(db, order_id)
    _require_warehouse_access(order, current_user)

    if order.status != "Picked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Picked orders can be packed",
        )

    old_value = _order_snapshot(order)
    order.status = "Packed"

    try:
        _write_audit(db, current_user.id, "PACK", order, old_value)
        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise


def dispatch_sales_order(
    db: Session,
    order_id: int,
    courier_name: str,
    tracking_number: str,
    current_user: User,
) -> SalesOrder:
    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found",
        )

    _require_warehouse_access(order, current_user)

    if order.status != "Packed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Packed orders can be dispatched",
        )

    if not courier_name.strip() or not tracking_number.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Courier name and tracking number are required",
        )

    duplicate_tracking = (
        db.query(SalesOrder)
        .filter(SalesOrder.tracking_number == tracking_number)
        .first()
    )
    if duplicate_tracking:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tracking number already exists",
        )

    old_value = _order_snapshot(order)

    try:
        locked_inventory = {}

        for item in order.items:
            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == order.warehouse_id,
                )
                .with_for_update()
                .first()
            )

            if (
                inventory is None
                or inventory.quantity_reserved < item.quantity
                or inventory.quantity_on_hand < item.quantity
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Reserved or on-hand stock is inconsistent for product {item.product_id}",
                )

            locked_inventory[item.product_id] = inventory

        for item in order.items:
            inventory = locked_inventory[item.product_id]
            inventory.quantity_on_hand -= item.quantity
            inventory.quantity_reserved -= item.quantity
            inventory.updated_at = datetime.utcnow()

            db.add(
                StockMovement(
                    product_id=item.product_id,
                    warehouse_id=order.warehouse_id,
                    movement_type="Sales Dispatch",
                    quantity=-item.quantity,
                    reference_id=order.id,
                    balance_after=inventory.quantity_on_hand,
                    performed_by=current_user.id,
                    created_by=current_user.id,
                )
            )

        order.status = "Dispatched"
        order.courier_name = courier_name.strip()
        order.tracking_number = tracking_number.strip()
        order.dispatched_at = datetime.utcnow()

        db.flush()
        _write_audit(
            db,
            current_user.id,
            "DISPATCH",
            order,
            old_value=old_value,
        )
        db.commit()
        db.refresh(order)
        return order

    except Exception:
        db.rollback()
        raise


def deliver_sales_order(
    db: Session,
    order_id: int,
    current_user: User,
) -> SalesOrder:
    order = _get_order(db, order_id)
    _require_warehouse_access(order, current_user)

    if order.status != "Dispatched":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Dispatched orders can be delivered",
        )

    old_value = _order_snapshot(order)
    order.status = "Delivered"
    order.delivered_at = datetime.utcnow()

    try:
        _write_audit(db, current_user.id, "DELIVER", order, old_value)
        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise
