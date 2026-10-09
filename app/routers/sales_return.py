from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    require_admin_or_inventory_manager,
)
from app.database import get_db
from app.models.sales_return import SalesReturn
from app.models.user import User
from app.schemas.sales_return import (
    ReturnInspection,
    ReturnReject,
    ReturnStatusResponse,
    SalesReturnCreate,
    SalesReturnResponse,
)
from app.services.email_service import send_email
from app.services.sales_return_service import (
    create_sales_return,
    get_sales_return,
    inspect_sales_return,
    list_sales_returns,
    refund_sales_return,
    reject_sales_return,
)

router = APIRouter(
    prefix="/sales-returns",
    tags=["Sales Returns and Refunds"],
)


@router.post(
    "",
    response_model=SalesReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return(
    payload: SalesReturnCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return create_sales_return(db, payload, current_user)


@router.get(
    "",
    response_model=list[SalesReturnResponse],
)
def get_returns(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    return_status: str | None = Query(default=None, alias="status"),
    sales_order_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return list_sales_returns(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        return_status=return_status,
        sales_order_id=sales_order_id,
    )


@router.get(
    "/{return_id}",
    response_model=SalesReturnResponse,
)
def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return get_sales_return(db, return_id, current_user)


@router.put(
    "/{return_id}/inspect",
    response_model=SalesReturnResponse,
)
def inspect_return(
    return_id: int,
    payload: ReturnInspection,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return inspect_sales_return(
        db, return_id, payload, current_user
    )


@router.put(
    "/{return_id}/refund",
    response_model=ReturnStatusResponse,
)
def refund_return(
    return_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    # Keep the existing refund service and its response contract.
    result = refund_sales_return(db, return_id, current_user)

    # Query the saved return after the service has completed the refund.
    sales_return = (
        db.query(SalesReturn)
        .filter(SalesReturn.id == return_id)
        .first()
    )

    if sales_return is not None and sales_return.sales_order is not None:
        order = sales_return.sales_order
        customer = order.customer

        if customer is not None and customer.email:
            background_tasks.add_task(
                send_email,
                customer.email,
                f"Refund processed for sales return #{sales_return.id}",
                (
                    f"Hello {customer.name},\n\n"
                    f"Your return for sales order {order.so_number} "
                    "has been processed.\n"
                    f"Refund amount: {sales_return.refund_amount}\n"
                    f"Return status: {sales_return.status}\n\n"
                    "Thank you."
                ),
            )

    return result


@router.put(
    "/{return_id}/reject",
    response_model=ReturnStatusResponse,
)
def reject_return(
    return_id: int,
    payload: ReturnReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_inventory_manager),
):
    return reject_sales_return(
        db,
        return_id,
        payload.rejection_reason,
        current_user,
    )