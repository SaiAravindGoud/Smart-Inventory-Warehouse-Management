from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin_or_inventory_manager,
    require_warehouse_staff,
)
from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import PaginatedResponse
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderReceive,
    PurchaseOrderStatusResponse,
)
from app.services.email_service import send_email

router = APIRouter(
    prefix="/purchase-orders",
    tags=["Purchase Orders"],
)


def generate_po_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"PO-{today}-"

    last_po = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.po_number.like(f"{prefix}%"))
        .order_by(PurchaseOrder.id.desc())
        .first()
    )

    sequence = 1
    if last_po:
        try:
            sequence = int(last_po.po_number.split("-")[-1]) + 1
        except ValueError:
            sequence = 1

    return f"{prefix}{sequence:04d}"


def calculate_total(items: list[PurchaseOrderItem]) -> Decimal:
    return sum(
        (
            Decimal(item.quantity_ordered) * Decimal(item.unit_cost)
            for item in items
        ),
        Decimal("0.00"),
    )


def build_po_response(po: PurchaseOrder) -> PurchaseOrderResponse:
    return PurchaseOrderResponse.model_validate(po)


def build_status_response(
    po: PurchaseOrder,
    message: str,
) -> PurchaseOrderStatusResponse:
    return PurchaseOrderStatusResponse(
        id=po.id,
        po_number=po.po_number,
        status=po.status,
        received_at=po.received_at,
        total_amount=po.total_amount,
        message=message,
    )


@router.post(
    "",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    try:
        supplier = (
            db.query(Supplier)
            .filter(Supplier.id == payload.supplier_id)
            .first()
        )

        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

        if not supplier.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive supplier cannot be used for a purchase order",
            )

        warehouse = (
            db.query(Warehouse)
            .filter(Warehouse.id == payload.warehouse_id)
            .first()
        )

        if warehouse is None:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        if not warehouse.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive warehouse cannot be used for a purchase order",
            )

        po_items = []
        seen_products = set()

        for item in payload.items:
            if item.product_id in seen_products:
                raise HTTPException(
                    status_code=422,
                    detail=f"Product {item.product_id} appears more than once",
                )
            seen_products.add(item.product_id)

            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .first()
            )

            if product is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found",
                )

            if not product.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product {item.product_id} is inactive",
                )

            po_items.append(
                PurchaseOrderItem(
                    product_id=item.product_id,
                    quantity_ordered=item.quantity_ordered,
                    quantity_received=0,
                    unit_cost=item.unit_cost,
                )
            )

        expected_date = payload.expected_delivery_date
        if expected_date is None:
            expected_date = date.today() + timedelta(
                days=supplier.lead_time_days
            )

        purchase_order = PurchaseOrder(
            po_number=generate_po_number(db),
            supplier_id=payload.supplier_id,
            warehouse_id=payload.warehouse_id,
            expected_delivery_date=expected_date,
            total_amount=Decimal("0.00"),
            status="Draft",
            created_by=current_user.id,
        )

        db.add(purchase_order)
        db.flush()

        for item in po_items:
            item.purchase_order_id = purchase_order.id
            db.add(item)

        db.flush()
        purchase_order.total_amount = calculate_total(po_items)

        db.commit()
        db.refresh(purchase_order)
        return build_po_response(purchase_order)

    except Exception:
        db.rollback()
        raise


@router.get(
    "",
    response_model=PaginatedResponse[PurchaseOrderResponse],
)
def list_purchase_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    po_status: str | None = Query(None, alias="status"),
    supplier_id: int | None = Query(None, gt=0),
    warehouse_id: int | None = Query(None, gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PurchaseOrder)

    if search:
        query = query.filter(
            or_(PurchaseOrder.po_number.ilike(f"%{search}%"))
        )

    if po_status:
        query = query.filter(PurchaseOrder.status == po_status)

    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)

    if warehouse_id:
        query = query.filter(PurchaseOrder.warehouse_id == warehouse_id)

    if start_date:
        query = query.filter(
            PurchaseOrder.expected_delivery_date >= start_date
        )

    if end_date:
        query = query.filter(
            PurchaseOrder.expected_delivery_date <= end_date
        )

    if current_user.role == "Warehouse Staff":
        if current_user.assigned_warehouse_id is None:
            raise HTTPException(
                status_code=403,
                detail="Warehouse Staff is not assigned to a warehouse",
            )
        query = query.filter(
            PurchaseOrder.warehouse_id
            == current_user.assigned_warehouse_id
        )

    total = query.count()
    orders = (
        query.order_by(PurchaseOrder.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return PaginatedResponse(
        items=[build_po_response(po) for po in orders],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{po_id}",
    response_model=PurchaseOrderResponse,
)
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()

    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if (
        current_user.role == "Warehouse Staff"
        and po.warehouse_id != current_user.assigned_warehouse_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can access only purchase orders for your assigned warehouse",
        )

    return build_po_response(po)


@router.put(
    "/{po_id}/approve",
    response_model=PurchaseOrderStatusResponse,
)
def approve_purchase_order(
    po_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    try:
        po = (
            db.query(PurchaseOrder)
            .filter(PurchaseOrder.id == po_id)
            .with_for_update()
            .first()
        )

        if po is None:
            raise HTTPException(
                status_code=404,
                detail="Purchase order not found",
            )

        if po.status != "Draft":
            raise HTTPException(
                status_code=400,
                detail="Only Draft purchase orders can be approved",
            )

        po.status = "Approved"
        db.commit()
        db.refresh(po)

        # Schedule supplier notification after the approval is committed.
        supplier = (
            db.query(Supplier)
            .filter(Supplier.id == po.supplier_id)
            .first()
        )

        if supplier and supplier.email:
            background_tasks.add_task(
                send_email,
                supplier.email,
                f"Purchase order {po.po_number} approved",
                (
                    f"Hello {supplier.name},\n\n"
                    f"Purchase order {po.po_number} has been approved.\n"
                    f"Expected delivery date: {po.expected_delivery_date}\n"
                    f"Total amount: {po.total_amount}\n"
                    f"Status: {po.status}\n\n"
                    "Please prepare the items for delivery."
                ),
            )

        return build_status_response(
            po,
            "Purchase order approved successfully",
        )

    except Exception:
        db.rollback()
        raise


@router.post(
    "/{po_id}/receive",
    response_model=PurchaseOrderStatusResponse,
)
def receive_purchase_order(
    po_id: int,
    payload: PurchaseOrderReceive,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_warehouse_staff),
):
    try:
        po = (
            db.query(PurchaseOrder)
            .filter(PurchaseOrder.id == po_id)
            .with_for_update()
            .first()
        )

        if po is None:
            raise HTTPException(
                status_code=404,
                detail="Purchase order not found",
            )

        if (
            current_user.role == "Warehouse Staff"
            and po.warehouse_id != current_user.assigned_warehouse_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You can receive stock only for your assigned warehouse",
            )

        if po.status not in {"Approved", "Partially Received"}:
            raise HTTPException(
                status_code=400,
                detail="Only Approved or Partially Received purchase orders can be received",
            )

        warehouse = (
            db.query(Warehouse)
            .filter(Warehouse.id == po.warehouse_id)
            .with_for_update()
            .first()
        )

        if warehouse is None:
            raise HTTPException(
                status_code=404,
                detail="Purchase order warehouse not found",
            )

        if not warehouse.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive warehouse cannot receive stock",
            )

        receive_items = {}
        for item in payload.items:
            if item.product_id in receive_items:
                raise HTTPException(
                    status_code=422,
                    detail=f"Product {item.product_id} appears more than once",
                )
            receive_items[item.product_id] = item.quantity_received

        po_items = (
            db.query(PurchaseOrderItem)
            .filter(PurchaseOrderItem.purchase_order_id == po.id)
            .with_for_update()
            .all()
        )
        po_item_map = {item.product_id: item for item in po_items}

        for product_id, quantity in receive_items.items():
            if product_id not in po_item_map:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product {product_id} is not part of this purchase order",
                )

            po_item = po_item_map[product_id]
            remaining = po_item.quantity_ordered - po_item.quantity_received

            if quantity <= 0 or quantity > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid quantity for product {product_id}. "
                        f"Remaining quantity is {remaining}."
                    ),
                )

        inventories = (
            db.query(Inventory)
            .filter(Inventory.warehouse_id == po.warehouse_id)
            .with_for_update()
            .all()
        )
        current_units = sum(item.quantity_on_hand for item in inventories)
        incoming_units = sum(receive_items.values())

        if current_units + incoming_units > warehouse.capacity:
            raise HTTPException(
                status_code=400,
                detail="Receiving this stock would exceed warehouse capacity",
            )

        for product_id, quantity in receive_items.items():
            po_item = po_item_map[product_id]

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == product_id,
                    Inventory.warehouse_id == po.warehouse_id,
                )
                .with_for_update()
                .first()
            )

            if inventory is None:
                inventory = Inventory(
                    product_id=product_id,
                    warehouse_id=po.warehouse_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    created_by=current_user.id,
                )
                db.add(inventory)
                db.flush()

            inventory.quantity_on_hand += quantity
            po_item.quantity_received += quantity

            db.add(
                StockMovement(
                    product_id=product_id,
                    warehouse_id=po.warehouse_id,
                    movement_type="Receipt",
                    quantity=quantity,
                    reference_id=po.id,
                    balance_after=inventory.quantity_on_hand,
                    unit_cost=po_item.unit_cost,
                    performed_by=current_user.id,
                )
            )

        all_received = all(
            item.quantity_received >= item.quantity_ordered
            for item in po_items
        )

        if all_received:
            po.status = "Received"
            po.received_at = datetime.utcnow()
        else:
            po.status = "Partially Received"

        db.commit()
        db.refresh(po)

        return build_status_response(
            po,
            "Purchase order stock received successfully",
        )

    except Exception:
        db.rollback()
        raise


@router.put(
    "/{po_id}/cancel",
    response_model=PurchaseOrderStatusResponse,
)
def cancel_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    try:
        po = (
            db.query(PurchaseOrder)
            .filter(PurchaseOrder.id == po_id)
            .with_for_update()
            .first()
        )

        if po is None:
            raise HTTPException(
                status_code=404,
                detail="Purchase order not found",
            )

        if po.status not in {"Draft", "Approved"}:
            raise HTTPException(
                status_code=400,
                detail="Only Draft or Approved purchase orders can be cancelled",
            )

        received_item = (
            db.query(PurchaseOrderItem)
            .filter(
                PurchaseOrderItem.purchase_order_id == po.id,
                PurchaseOrderItem.quantity_received > 0,
            )
            .first()
        )

        if received_item is not None:
            raise HTTPException(
                status_code=400,
                detail="Purchase order cannot be cancelled after stock has been received",
            )

        po.status = "Cancelled"
        db.commit()
        db.refresh(po)

        return build_status_response(
            po,
            "Purchase order cancelled successfully",
        )

    except Exception:
        db.rollback()
        raise