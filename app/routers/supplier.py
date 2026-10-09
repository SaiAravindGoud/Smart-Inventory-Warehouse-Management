from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin,
    require_admin_or_inventory_manager,
)
from app.database import get_db
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.supplier import (
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)


router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    supplier_data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    existing_code = (
        db.query(Supplier)
        .filter(Supplier.supplier_code == supplier_data.supplier_code)
        .first()
    )

    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier with this code already exists",
        )

    existing_email = (
        db.query(Supplier)
        .filter(Supplier.email == supplier_data.email)
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier with this email already exists",
        )

    supplier = Supplier(
        supplier_code=supplier_data.supplier_code,
        name=supplier_data.name,
        email=supplier_data.email,
        phone=supplier_data.phone,
        gst_number=supplier_data.gst_number,
        address=supplier_data.address,
        lead_time_days=supplier_data.lead_time_days,
        is_active=supplier_data.is_active,
        created_by=current_user.id,
    )

    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return supplier


@router.get(
    "",
    response_model=PaginatedResponse[SupplierResponse],
)
def list_suppliers(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Supplier)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Supplier.supplier_code.ilike(pattern),
                Supplier.name.ilike(pattern),
                Supplier.email.ilike(pattern),
                Supplier.phone.ilike(pattern),
                Supplier.gst_number.ilike(pattern),
            )
        )

    if is_active is not None:
        query = query.filter(Supplier.is_active.is_(is_active))

    total = query.count()

    suppliers = (
        query.order_by(Supplier.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return PaginatedResponse(
        items=suppliers,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    return supplier


@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def update_supplier(
    supplier_id: int,
    supplier_data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    if (
        supplier_data.supplier_code is not None
        and supplier_data.supplier_code != supplier.supplier_code
    ):
        existing_code = (
            db.query(Supplier)
            .filter(
                Supplier.supplier_code == supplier_data.supplier_code,
                Supplier.id != supplier_id,
            )
            .first()
        )

        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier with this code already exists",
            )

        supplier.supplier_code = supplier_data.supplier_code

    if (
        supplier_data.email is not None
        and supplier_data.email != supplier.email
    ):
        existing_email = (
            db.query(Supplier)
            .filter(
                Supplier.email == supplier_data.email,
                Supplier.id != supplier_id,
            )
            .first()
        )

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier with this email already exists",
            )

        supplier.email = supplier_data.email

    if supplier_data.name is not None:
        supplier.name = supplier_data.name

    if supplier_data.phone is not None:
        supplier.phone = supplier_data.phone

    if supplier_data.gst_number is not None:
        supplier.gst_number = supplier_data.gst_number

    if supplier_data.address is not None:
        supplier.address = supplier_data.address

    if supplier_data.lead_time_days is not None:
        supplier.lead_time_days = supplier_data.lead_time_days

    if supplier_data.is_active is not None:
        supplier.is_active = supplier_data.is_active

    db.commit()
    db.refresh(supplier)

    return supplier


@router.delete(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    supplier.is_active = False

    db.commit()
    db.refresh(supplier)

    return supplier