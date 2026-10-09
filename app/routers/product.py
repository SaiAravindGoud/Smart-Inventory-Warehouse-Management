from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin_or_inventory_manager,
)
from app.database import get_db
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.product import (
    ProductCreate,
    ProductInventoryResponse,
    ProductResponse,
    ProductUpdate,
)


router = APIRouter(prefix="/products", tags=["Products"])


def build_product_response(
    product: Product,
    db: Session,
) -> ProductResponse:
    inventory_rows = (
        db.query(Inventory)
        .filter(Inventory.product_id == product.id)
        .all()
    )

    inventory = [
        ProductInventoryResponse(
            warehouse_id=row.warehouse_id,
            quantity_on_hand=row.quantity_on_hand,
            quantity_reserved=row.quantity_reserved,
            quantity_available=row.quantity_available,
        )
        for row in inventory_rows
    ]

    total_stock = sum(row.quantity_on_hand for row in inventory_rows)

    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        barcode=product.barcode,
        category_id=product.category_id,
        unit=product.unit,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        reorder_level=product.reorder_level,
        reorder_quantity=product.reorder_quantity,
        preferred_supplier_id=product.preferred_supplier_id,
        is_active=product.is_active,
        inventory=inventory,
        total_stock=total_stock,
        created_at=product.created_at,
        updated_at=product.updated_at,
        created_by=product.created_by,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    existing_sku = (
        db.query(Product)
        .filter(Product.sku == product_data.sku)
        .first()
    )

    if existing_sku:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this SKU already exists",
        )

    if product_data.barcode:
        existing_barcode = (
            db.query(Product)
            .filter(Product.barcode == product_data.barcode)
            .first()
        )

        if existing_barcode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this barcode already exists",
            )

    category = (
        db.query(Category)
        .filter(Category.id == product_data.category_id)
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    if not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create product under an inactive category",
        )

    if product_data.preferred_supplier_id is not None:
        supplier = (
            db.query(Supplier)
            .filter(Supplier.id == product_data.preferred_supplier_id)
            .first()
        )

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preferred supplier not found",
            )

        if not supplier.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preferred supplier is inactive",
            )

    product = Product(
        name=product_data.name,
        sku=product_data.sku,
        barcode=product_data.barcode,
        category_id=product_data.category_id,
        unit=product_data.unit,
        cost_price=product_data.cost_price,
        selling_price=product_data.selling_price,
        reorder_level=product_data.reorder_level,
        reorder_quantity=product_data.reorder_quantity,
        preferred_supplier_id=product_data.preferred_supplier_id,
        is_active=product_data.is_active,
        created_by=current_user.id,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return build_product_response(product, db)


@router.get(
    "",
    response_model=PaginatedResponse[ProductResponse],
)
def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    sku: str | None = Query(default=None),
    category_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Product)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_pattern),
                Product.sku.ilike(search_pattern),
                Product.barcode.ilike(search_pattern),
            )
        )

    if sku:
        query = query.filter(Product.sku.ilike(f"%{sku}%"))

    if category_id is not None:
        query = query.filter(Product.category_id == category_id)

    if supplier_id is not None:
        query = query.filter(
            Product.preferred_supplier_id == supplier_id
        )

    if is_active is not None:
        query = query.filter(Product.is_active.is_(is_active))

    total = query.count()

    products = (
        query.order_by(Product.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        build_product_response(product, db)
        for product in products
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return build_product_response(product, db)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if product_data.sku is not None and product_data.sku != product.sku:
        existing_sku = (
            db.query(Product)
            .filter(
                Product.sku == product_data.sku,
                Product.id != product_id,
            )
            .first()
        )

        if existing_sku:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this SKU already exists",
            )

        product.sku = product_data.sku

    if (
        product_data.barcode is not None
        and product_data.barcode != product.barcode
    ):
        existing_barcode = (
            db.query(Product)
            .filter(
                Product.barcode == product_data.barcode,
                Product.id != product_id,
            )
            .first()
        )

        if existing_barcode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this barcode already exists",
            )

        product.barcode = product_data.barcode

    if product_data.category_id is not None:
        category = (
            db.query(Category)
            .filter(Category.id == product_data.category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        if not category.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign product to an inactive category",
            )

        product.category_id = product_data.category_id

    if product_data.preferred_supplier_id is not None:
        supplier = (
            db.query(Supplier)
            .filter(Supplier.id == product_data.preferred_supplier_id)
            .first()
        )

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preferred supplier not found",
            )

        if not supplier.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preferred supplier is inactive",
            )

        product.preferred_supplier_id = product_data.preferred_supplier_id

    if product_data.name is not None:
        product.name = product_data.name

    if product_data.unit is not None:
        product.unit = product_data.unit

    if product_data.cost_price is not None:
        product.cost_price = product_data.cost_price

    if product_data.selling_price is not None:
        product.selling_price = product_data.selling_price

    if product_data.reorder_level is not None:
        product.reorder_level = product_data.reorder_level

    if product_data.reorder_quantity is not None:
        product.reorder_quantity = product_data.reorder_quantity

    if product_data.is_active is not None:
        if not product_data.is_active and product.is_active:
            stock_exists = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == product.id,
                    Inventory.quantity_on_hand > 0,
                )
                .first()
            )

            if stock_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Product with stock cannot be deactivated",
                )

        product.is_active = product_data.is_active

    final_cost = product.cost_price
    final_selling = product.selling_price

    if final_selling < final_cost:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selling price cannot be less than cost price",
        )

    db.commit()
    db.refresh(product)

    return build_product_response(product, db)


@router.delete(
    "/{product_id}",
    response_model=ProductResponse,
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    stock_exists = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product.id,
            Inventory.quantity_on_hand > 0,
        )
        .first()
    )

    if stock_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with stock cannot be deactivated",
        )

    product.is_active = False

    db.commit()
    db.refresh(product)

    return build_product_response(product, db)