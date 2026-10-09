
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.inventory import Inventory
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.sales_return import SalesReturn
from app.models.sales_return_item import SalesReturnItem
from app.models.stock_movement import StockMovement
from app.models.user import User


GST_RATE = Decimal("0.18")
MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _require_manager(user: User) -> None:
    if user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inventory Manager access required",
        )


def _snapshot(sales_return: SalesReturn) -> dict:
    return {
        "sales_order_id": sales_return.sales_order_id,
        "status": sales_return.status,
        "reason": sales_return.reason,
        "refund_amount": str(sales_return.refund_amount),
        "rejection_reason": sales_return.rejection_reason,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "condition": item.condition,
            }
            for item in sales_return.items
        ],
    }


def _write_audit(
    db: Session,
    user_id: int,
    action: str,
    sales_return: SalesReturn,
    old_value: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type="SalesReturn",
            entity_id=sales_return.id,
            old_value=old_value,
            new_value=_snapshot(sales_return),
            timestamp=datetime.utcnow(),
        )
    )


def _get_return(db: Session, return_id: int) -> SalesReturn:
    sales_return = (
        db.query(SalesReturn)
        .filter(SalesReturn.id == return_id)
        .with_for_update()
        .first()
    )

    if sales_return is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales return not found",
        )

    return sales_return


def create_sales_return(
    db: Session,
    payload,
    current_user: User,
) -> SalesReturn:
    _require_manager(current_user)

    product_ids = [item.product_id for item in payload.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each product may appear only once in a return request",
        )

    try:
        order = (
            db.query(SalesOrder)
            .filter(SalesOrder.id == payload.sales_order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sales order not found",
            )

        if order.status != "Delivered" or order.delivered_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only delivered orders can be returned",
            )

        if order.delivered_at < datetime.utcnow() - timedelta(days=7):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Returns are allowed only within 7 days of delivery",
            )

        order_items = (
            db.query(SalesOrderItem)
            .filter(SalesOrderItem.sales_order_id == order.id)
            .with_for_update()
            .all()
        )
        original_items = {item.product_id: item for item in order_items}

        existing_returns = (
            db.query(SalesReturn)
            .filter(
                SalesReturn.sales_order_id == order.id,
                SalesReturn.status != "Rejected",
            )
            .with_for_update()
            .all()
        )

        already_returned: dict[int, int] = {}
        for existing_return in existing_returns:
            for existing_item in existing_return.items:
                already_returned[existing_item.product_id] = (
                    already_returned.get(existing_item.product_id, 0)
                    + existing_item.quantity
                )

        for requested_item in payload.items:
            original = original_items.get(requested_item.product_id)

            if original is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Product {requested_item.product_id} "
                        "was not part of this order"
                    ),
                )

            remaining = (
                original.quantity
                - already_returned.get(requested_item.product_id, 0)
            )

            if requested_item.quantity > remaining:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Return quantity for product "
                        f"{requested_item.product_id} exceeds the "
                        f"remaining eligible quantity of {remaining}"
                    ),
                )

        sales_return = SalesReturn(
            sales_order_id=order.id,
            reason=payload.reason.strip(),
            status="Requested",
            refund_amount=Decimal("0.00"),
            created_by=current_user.id,
        )
        db.add(sales_return)
        db.flush()

        for requested_item in payload.items:
            db.add(
                SalesReturnItem(
                    sales_return_id=sales_return.id,
                    product_id=requested_item.product_id,
                    quantity=requested_item.quantity,
                    condition=requested_item.condition,
                    created_by=current_user.id,
                )
            )

        db.flush()
        _write_audit(
            db, current_user.id, "CREATE_RETURN", sales_return
        )
        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise


def inspect_sales_return(
    db: Session,
    return_id: int,
    payload,
    current_user: User,
) -> SalesReturn:
    """Record inspection results without refunding or restocking."""
    _require_manager(current_user)

    try:
        sales_return = _get_return(db, return_id)

        if sales_return.status != "Requested":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only Requested returns can be inspected",
            )

        requested_ids = {item.product_id for item in sales_return.items}
        inspected_ids = [item.product_id for item in payload.items]

        if (
            len(inspected_ids) != len(set(inspected_ids))
            or set(inspected_ids) != requested_ids
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Inspection must include every returned product "
                    "exactly once"
                ),
            )

        old_value = _snapshot(sales_return)
        conditions = {
            item.product_id: item.condition for item in payload.items
        }

        for return_item in sales_return.items:
            return_item.condition = conditions[return_item.product_id]

        sales_return.status = "Inspected"

        db.flush()
        _write_audit(
            db,
            current_user.id,
            "INSPECT_RETURN",
            sales_return,
            old_value=old_value,
        )
        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise


def refund_sales_return(
    db: Session,
    return_id: int,
    current_user: User,
) -> SalesReturn:
    """Refund an inspected return and restock only Good items."""
    _require_manager(current_user)

    try:
        sales_return = _get_return(db, return_id)

        if sales_return.status != "Inspected":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only Inspected returns can be refunded",
            )

        order = (
            db.query(SalesOrder)
            .filter(SalesOrder.id == sales_return.sales_order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original sales order not found",
            )

        original_items = {
            item.product_id: item
            for item in (
                db.query(SalesOrderItem)
                .filter(SalesOrderItem.sales_order_id == order.id)
                .all()
            )
        }

        old_value = _snapshot(sales_return)
        refund_subtotal = Decimal("0.00")

        for return_item in sales_return.items:
            original_item = original_items.get(return_item.product_id)

            if original_item is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Original sales order item was not found",
                )

            # Refund original item price for each accepted return quantity,
            # including the order's 18% GST.
            refund_subtotal += (
                Decimal(str(original_item.unit_price))
                * return_item.quantity
            )

            if return_item.condition == "Good":
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.product_id == return_item.product_id,
                        Inventory.warehouse_id == order.warehouse_id,
                    )
                    .with_for_update()
                    .first()
                )

                if inventory is None:
                    inventory = Inventory(
                        product_id=return_item.product_id,
                        warehouse_id=order.warehouse_id,
                        quantity_on_hand=0,
                        quantity_reserved=0,
                        created_by=current_user.id,
                    )
                    db.add(inventory)
                    db.flush()

                inventory.quantity_on_hand += return_item.quantity
                inventory.updated_at = datetime.utcnow()

                db.add(
                    StockMovement(
                        product_id=return_item.product_id,
                        warehouse_id=order.warehouse_id,
                        movement_type="Sales Return",
                        quantity=return_item.quantity,
                        reference_id=sales_return.id,
                        balance_after=inventory.quantity_on_hand,
                        performed_by=current_user.id,
                        created_by=current_user.id,
                    )
                )

            # Damaged items are recorded on the return but never added
            # to sellable inventory.

        sales_return.refund_amount = _money(
            refund_subtotal * (Decimal("1.00") + GST_RATE)
        )
        sales_return.status = "Refunded"

        db.flush()
        _write_audit(
            db,
            current_user.id,
            "REFUND_RETURN",
            sales_return,
            old_value=old_value,
        )
        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise


def reject_sales_return(
    db: Session,
    return_id: int,
    rejection_reason: str,
    current_user: User,
) -> SalesReturn:
    _require_manager(current_user)

    try:
        sales_return = _get_return(db, return_id)

        if sales_return.status != "Requested":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only Requested returns can be rejected",
            )

        reason = rejection_reason.strip()
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Rejection reason cannot be empty",
            )

        old_value = _snapshot(sales_return)
        sales_return.status = "Rejected"
        sales_return.rejection_reason = reason

        db.flush()
        _write_audit(
            db,
            current_user.id,
            "REJECT_RETURN",
            sales_return,
            old_value=old_value,
        )
        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise


def list_sales_returns(
    db: Session,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
    return_status: str | None = None,
    sales_order_id: int | None = None,
) -> list[SalesReturn]:
    _require_manager(current_user)

    query = db.query(SalesReturn)

    if return_status:
        query = query.filter(SalesReturn.status == return_status)

    if sales_order_id is not None:
        query = query.filter(
            SalesReturn.sales_order_id == sales_order_id
        )

    return (
        query.order_by(SalesReturn.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_sales_return(
    db: Session,
    return_id: int,
    current_user: User,
) -> SalesReturn:
    _require_manager(current_user)
    return _get_return(db, return_id)
