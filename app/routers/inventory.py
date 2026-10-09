from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    InventoryDetailResponse,
    InventoryResponse,
    StockMovementResponse,
)


router = APIRouter(tags=["Inventory"])


@router.get(
    "/inventory",
    response_model=list[InventoryResponse],
)
def list_inventory(
    product_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    low_stock: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Inventory)

    if product_id is not None:
        query = query.filter(Inventory.product_id == product_id)

    if warehouse_id is not None:
        query = query.filter(Inventory.warehouse_id == warehouse_id)

    if low_stock:
        query = query.join(
            Product,
            Product.id == Inventory.product_id,
        ).filter(
            Inventory.quantity_available < Product.reorder_level
        )

    inventory_rows = (
        query.order_by(Inventory.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return inventory_rows


@router.get(
    "/inventory/{product_id}/{warehouse_id}",
    response_model=InventoryDetailResponse,
)
def get_inventory(
    product_id: int,
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inventory = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == warehouse_id,
        )
        .first()
    )

    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found",
        )

    return InventoryDetailResponse(
        product_id=inventory.product_id,
        warehouse_id=inventory.warehouse_id,
        quantity_on_hand=inventory.quantity_on_hand,
        quantity_reserved=inventory.quantity_reserved,
        quantity_available=inventory.quantity_available,
    )


@router.get(
    "/stock-movements",
    response_model=list[StockMovementResponse],
)
def list_stock_movements(
    product_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    movement_type: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date cannot be after end_date",
        )

    query = db.query(StockMovement)

    if product_id is not None:
        query = query.filter(
            StockMovement.product_id == product_id
        )

    if warehouse_id is not None:
        query = query.filter(
            StockMovement.warehouse_id == warehouse_id
        )

    if movement_type:
        query = query.filter(
            StockMovement.movement_type == movement_type
        )

    if start_date:
        query = query.filter(
            StockMovement.created_at >= start_date
        )

    if end_date:
        query = query.filter(
            StockMovement.created_at <= end_date
        )

    movements = (
        query.order_by(StockMovement.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return movements