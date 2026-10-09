from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerUpdate


def _customer_snapshot(customer: Customer) -> dict:
    return {
        "customer_code": customer.customer_code,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "credit_limit": str(customer.credit_limit),
        "is_active": customer.is_active,
    }


def _write_audit_log(
    db: Session,
    user_id: int,
    action: str,
    customer: Customer,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type="Customer",
            entity_id=customer.id,
            old_value=old_value,
            new_value=new_value,
            timestamp=datetime.utcnow(),
        )
    )


def create_customer(
    db: Session,
    payload: CustomerCreate,
    current_user: User,
) -> Customer:
    if current_user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inventory Manager access required",
        )

    existing = (
        db.query(Customer)
        .filter(
            or_(
                Customer.customer_code == payload.customer_code,
                Customer.email == str(payload.email),
            )
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer code or email already exists",
        )

    customer = Customer(
        customer_code=payload.customer_code,
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        address=payload.address,
        credit_limit=payload.credit_limit,
        is_active=True,
        created_by=current_user.id,
    )

    try:
        db.add(customer)
        db.flush()

        _write_audit_log(
            db=db,
            user_id=current_user.id,
            action="CREATE",
            customer=customer,
            new_value=_customer_snapshot(customer),
        )

        db.commit()
        db.refresh(customer)
        return customer
    except Exception:
        db.rollback()
        raise


def list_customers(
    db: Session,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> list[Customer]:
    query = db.query(Customer)

    if current_user.role == "Warehouse Staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Warehouse Staff cannot access customer management",
        )

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Customer.customer_code.ilike(search_term),
                Customer.name.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.phone.ilike(search_term),
            )
        )

    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)

    return (
        query.order_by(Customer.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_customer(
    db: Session,
    customer_id: int,
    current_user: User,
) -> Customer:
    if current_user.role == "Warehouse Staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Warehouse Staff cannot access customer management",
        )

    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return customer


def update_customer(
    db: Session,
    customer_id: int,
    payload: CustomerUpdate,
    current_user: User,
) -> Customer:
    if current_user.role not in {"Admin", "Inventory Manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Inventory Manager access required",
        )

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    changes = payload.model_dump(exclude_unset=True)

    for field in ("customer_code", "email"):
        value = changes.get(field)
        if value is not None:
            if field == "email":
                value = str(value)
                changes[field] = value

            duplicate = (
                db.query(Customer)
                .filter(
                    getattr(Customer, field) == value,
                    Customer.id != customer_id,
                )
                .first()
            )
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{field.replace('_', ' ').capitalize()} already exists",
                )

    old_value = _customer_snapshot(customer)

    for field, value in changes.items():
        setattr(customer, field, value)

    try:
        db.flush()

        _write_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            customer=customer,
            old_value=old_value,
            new_value=_customer_snapshot(customer),
        )

        db.commit()
        db.refresh(customer)
        return customer
    except Exception:
        db.rollback()
        raise
