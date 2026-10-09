from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.inventory import Inventory
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import PaginatedResponse
from app.schemas.warehouse import (
    InventorySummary,
    WarehouseCreate,
    WarehouseInventoryResponse,
    WarehouseResponse,
    WarehouseUpdate,
)


router = APIRouter(prefix="/warehouses", tags=["Warehouses"])


@router.post(
    "",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_warehouse(
    warehouse_data: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = (
        db.query(Warehouse)
        .filter(Warehouse.warehouse_code == warehouse_data.warehouse_code)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse with this code already exists",
        )

    if warehouse_data.manager_id is not None:
        manager = (
            db.query(User)
            .filter(User.id == warehouse_data.manager_id)
            .first()
        )

        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse manager not found",
            )

        if not manager.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse manager is inactive",
            )

    warehouse = Warehouse(
        warehouse_code=warehouse_data.warehouse_code,
        name=warehouse_data.name,
        city=warehouse_data.city,
        address=warehouse_data.address,
        capacity=warehouse_data.capacity,
        manager_id=warehouse_data.manager_id,
        is_active=warehouse_data.is_active,
        created_by=current_user.id,
    )

    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    return warehouse


@router.get(
    "",
    response_model=PaginatedResponse[WarehouseResponse],
)
def list_warehouses(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    city: str | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Warehouse)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Warehouse.warehouse_code.ilike(pattern),
                Warehouse.name.ilike(pattern),
                Warehouse.city.ilike(pattern),
                Warehouse.address.ilike(pattern),
            )
        )

    if city:
        query = query.filter(Warehouse.city.ilike(f"%{city}%"))

    if is_active is not None:
        query = query.filter(Warehouse.is_active.is_(is_active))

    total = query.count()

    warehouses = (
        query.order_by(Warehouse.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return PaginatedResponse(
        items=warehouses,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{warehouse_id}",
    response_model=WarehouseResponse,
)
def get_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == warehouse_id)
        .first()
    )

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    return warehouse


@router.put(
    "/{warehouse_id}",
    response_model=WarehouseResponse,
)
def update_warehouse(
    warehouse_id: int,
    warehouse_data: WarehouseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == warehouse_id)
        .first()
    )

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    if (
        warehouse_data.warehouse_code is not None
        and warehouse_data.warehouse_code != warehouse.warehouse_code
    ):
        existing = (
            db.query(Warehouse)
            .filter(
                Warehouse.warehouse_code == warehouse_data.warehouse_code,
                Warehouse.id != warehouse_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Warehouse with this code already exists",
            )

        warehouse.warehouse_code = warehouse_data.warehouse_code

    if warehouse_data.manager_id is not None:
        manager = (
            db.query(User)
            .filter(User.id == warehouse_data.manager_id)
            .first()
        )

        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse manager not found",
            )

        if not manager.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse manager is inactive",
            )

        warehouse.manager_id = warehouse_data.manager_id

    if warehouse_data.name is not None:
        warehouse.name = warehouse_data.name

    if warehouse_data.city is not None:
        warehouse.city = warehouse_data.city

    if warehouse_data.address is not None:
        warehouse.address = warehouse_data.address

    if warehouse_data.capacity is not None:
        current_stock = (
            db.query(Inventory.quantity_on_hand)
            .filter(Inventory.warehouse_id == warehouse.id)
            .all()
        )

        total_stock = sum(row[0] for row in current_stock)

        if warehouse_data.capacity < total_stock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Warehouse capacity cannot be less than current "
                    f"stock ({total_stock})"
                ),
            )

        warehouse.capacity = warehouse_data.capacity

    if warehouse_data.is_active is not None:
        if not warehouse_data.is_active and warehouse.is_active:
            stock_exists = (
                db.query(Inventory)
                .filter(
                    Inventory.warehouse_id == warehouse.id,
                    Inventory.quantity_on_hand > 0,
                )
                .first()
            )

            if stock_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Warehouse with stock cannot be deactivated",
                )

        warehouse.is_active = warehouse_data.is_active

    db.commit()
    db.refresh(warehouse)

    return warehouse


@router.delete(
    "/{warehouse_id}",
    response_model=WarehouseResponse,
)
def delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == warehouse_id)
        .first()
    )

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    stock_exists = (
        db.query(Inventory)
        .filter(
            Inventory.warehouse_id == warehouse.id,
            Inventory.quantity_on_hand > 0,
        )
        .first()
    )

    if stock_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse with stock cannot be deleted",
        )

    warehouse.is_active = False

    db.commit()
    db.refresh(warehouse)

    return warehouse


@router.get(
    "/{warehouse_id}/inventory",
    response_model=WarehouseInventoryResponse,
)
def get_warehouse_inventory(
    warehouse_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    low_stock: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    warehouse = (
        db.query(Warehouse)
        .filter(Warehouse.id == warehouse_id)
        .first()
    )

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    query = (
        db.query(Inventory)
        .filter(Inventory.warehouse_id == warehouse_id)
    )

    if low_stock:
        query = query.join(Inventory.product).filter(
            Inventory.quantity_available < Inventory.product.reorder_level
        )

    total = query.count()

    inventory_rows = (
        query.order_by(Inventory.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        InventorySummary(
            product_id=row.product_id,
            quantity_on_hand=row.quantity_on_hand,
            quantity_reserved=row.quantity_reserved,
            quantity_available=row.quantity_available,
        )
        for row in inventory_rows
    ]

    return WarehouseInventoryResponse(
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.warehouse_code,
        warehouse_name=warehouse.name,
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )