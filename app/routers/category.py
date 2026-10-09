from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin_or_inventory_manager,
)
from app.database import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from app.schemas.common import PaginatedResponse


router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    existing = (
        db.query(Category)
        .filter(func.lower(Category.name) == category_data.name.lower())
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category with this name already exists",
        )

    category = Category(
        name=category_data.name,
        description=category_data.description,
        is_active=category_data.is_active,
        created_by=current_user.id,
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.get(
    "",
    response_model=PaginatedResponse[CategoryResponse],
)
def list_categories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Category)

    if not include_inactive:
        query = query.filter(Category.is_active.is_(True))

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Category.name.ilike(search_pattern),
                Category.description.ilike(search_pattern),
            )
        )

    total = query.count()

    categories = (
        query.order_by(Category.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return PaginatedResponse(
        items=categories,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id)
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    return category


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id)
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    if category_data.name is not None:
        existing = (
            db.query(Category)
            .filter(
                func.lower(Category.name) == category_data.name.lower(),
                Category.id != category_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this name already exists",
            )

        category.name = category_data.name

    if category_data.description is not None:
        category.description = category_data.description

    if category_data.is_active is not None:
        if not category_data.is_active:
            active_product_exists = (
                db.query(Product)
                .filter(
                    Product.category_id == category.id,
                    Product.is_active.is_(True),
                )
                .first()
            )

            if active_product_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Category with active products cannot be deactivated",
                )

        category.is_active = category_data.is_active

    category.updated_at = __import__("datetime").datetime.utcnow()

    db.commit()
    db.refresh(category)

    return category


@router.delete(
    "/{category_id}",
    response_model=CategoryResponse,
)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id)
        .first()
    )

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    active_product_exists = (
        db.query(Product)
        .filter(
            Product.category_id == category.id,
            Product.is_active.is_(True),
        )
        .first()
    )

    if active_product_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category with active products cannot be deleted",
        )

    category.is_active = False
    category.updated_at = __import__("datetime").datetime.utcnow()

    db.commit()
    db.refresh(category)

    return category