
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin_or_inventory_manager
from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.sales_return import SalesReturn
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


def format_money(value) -> str:
    return str(
        Decimal(str(value or 0)).quantize(Decimal("0.01"))
    )


def stock_by_product_query(db: Session):
    return (
        db.query(
            Inventory.product_id.label("product_id"),
            func.sum(
                Inventory.quantity_on_hand
            ).label("total_quantity"),
        )
        .group_by(Inventory.product_id)
        .subquery()
    )


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    total_products = (
        db.query(func.count(Product.id))
        .filter(Product.is_active.is_(True))
        .scalar()
        or 0
    )

    stock_value = (
        db.query(
            func.coalesce(
                func.sum(
                    Inventory.quantity_on_hand
                    * Product.cost_price
                ),
                0,
            )
        )
        .join(Product, Product.id == Inventory.product_id)
        .scalar()
    )

    stock_by_product = stock_by_product_query(db)

    low_stock_count = (
        db.query(func.count(Product.id))
        .outerjoin(
            stock_by_product,
            stock_by_product.c.product_id == Product.id,
        )
        .filter(
            Product.is_active.is_(True),
            func.coalesce(
                stock_by_product.c.total_quantity, 0
            ) < Product.reorder_level,
        )
        .scalar()
        or 0
    )

    pending_purchase_orders = (
        db.query(func.count(PurchaseOrder.id))
        .filter(
            PurchaseOrder.status.notin_(
                ["Received", "Cancelled"]
            )
        )
        .scalar()
        or 0
    )

    pending_sales_orders = (
        db.query(func.count(SalesOrder.id))
        .filter(
            SalesOrder.status.notin_(
                ["Delivered", "Cancelled"]
            )
        )
        .scalar()
        or 0
    )

    today_dispatches = (
        db.query(func.count(SalesOrder.id))
        .filter(
            SalesOrder.dispatched_at.isnot(None),
            func.date(SalesOrder.dispatched_at) == date.today(),
        )
        .scalar()
        or 0
    )

    return {
        "total_products": total_products,
        "total_stock_value": format_money(stock_value),
        "low_stock_count": low_stock_count,
        "pending_purchase_orders": pending_purchase_orders,
        "pending_sales_orders": pending_sales_orders,
        "today_dispatches": today_dispatches,
    }


@router.get("/stock-valuation")
def get_stock_valuation(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    rows = (
        db.query(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            func.coalesce(
                func.sum(
                    Inventory.quantity_on_hand
                    * Product.cost_price
                ),
                0,
            ).label("stock_value"),
            func.coalesce(
                func.sum(Inventory.quantity_on_hand),
                0,
            ).label("total_units"),
        )
        .outerjoin(
            Inventory,
            Inventory.warehouse_id == Warehouse.id,
        )
        .outerjoin(
            Product,
            Product.id == Inventory.product_id,
        )
        .group_by(Warehouse.id, Warehouse.name)
        .order_by(Warehouse.id)
        .all()
    )

    return [
        {
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "total_units": row.total_units,
            "stock_value": format_money(row.stock_value),
        }
        for row in rows
    ]


@router.get("/low-stock")
def get_low_stock_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    stock_by_product = stock_by_product_query(db)

    rows = (
        db.query(
            Product,
            func.coalesce(
                stock_by_product.c.total_quantity, 0
            ).label("total_quantity"),
        )
        .outerjoin(
            stock_by_product,
            stock_by_product.c.product_id == Product.id,
        )
        .filter(
            Product.is_active.is_(True),
            func.coalesce(
                stock_by_product.c.total_quantity, 0
            ) <= Product.reorder_level,
        )
        .order_by(Product.name)
        .all()
    )

    results = []

    for product, total_quantity in rows:
        reorder_quantity = product.reorder_quantity or 0

        suggested_quantity = max(
            reorder_quantity,
            product.reorder_level - total_quantity,
            0,
        )

        supplier = product.preferred_supplier

        results.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "total_quantity_on_hand": total_quantity,
                "reorder_level": product.reorder_level,
                "suggested_order_quantity": suggested_quantity,
                "preferred_supplier_id": product.preferred_supplier_id,
                "preferred_supplier_name": (
                    supplier.name if supplier else None
                ),
            }
        )

    return results


@router.get("/sales")
def get_sales_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    start_datetime = (
        datetime.combine(start_date, time.min)
        if start_date
        else None
    )

    end_datetime = (
        datetime.combine(end_date + timedelta(days=1), time.min)
        if end_date
        else None
    )

    orders_query = db.query(SalesOrder).filter(
        SalesOrder.status.in_(["Dispatched", "Delivered"])
    )

    if start_datetime:
        orders_query = orders_query.filter(
            SalesOrder.dispatched_at >= start_datetime
        )

    if end_datetime:
        orders_query = orders_query.filter(
            SalesOrder.dispatched_at < end_datetime
        )

    order_summary = orders_query.with_entities(
        func.count(SalesOrder.id),
        func.coalesce(func.sum(SalesOrder.grand_total), 0),
    ).first()

    returns_query = db.query(SalesReturn)

    if start_datetime:
        returns_query = returns_query.filter(
            SalesReturn.created_at >= start_datetime
        )

    if end_datetime:
        returns_query = returns_query.filter(
            SalesReturn.created_at < end_datetime
        )

    return_summary = returns_query.with_entities(
        func.count(SalesReturn.id),
        func.coalesce(func.sum(SalesReturn.refund_amount), 0),
    ).first()

    return {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "sales_order_count": order_summary[0] or 0,
        "sales_revenue": format_money(order_summary[1]),
        "return_count": return_summary[0] or 0,
        "refund_total": format_money(return_summary[1]),
    }


@router.get("/top-products")
def get_top_products_report(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    rows = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("sku"),
            func.coalesce(
                func.sum(SalesOrderItem.quantity), 0
            ).label("quantity_sold"),
            func.coalesce(
                func.sum(SalesOrderItem.line_total), 0
            ).label("sales_revenue"),
        )
        .join(
            SalesOrderItem,
            SalesOrderItem.product_id == Product.id,
        )
        .join(
            SalesOrder,
            SalesOrder.id == SalesOrderItem.sales_order_id,
        )
        .filter(
            SalesOrder.status.in_(["Dispatched", "Delivered"])
        )
        .group_by(
            Product.id,
            Product.name,
            Product.sku,
        )
        .order_by(
            func.sum(SalesOrderItem.quantity).desc(),
            Product.name.asc(),
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "sku": row.sku,
            "quantity_sold": row.quantity_sold,
            "sales_revenue": format_money(row.sales_revenue),
        }
        for row in rows
    ]


@router.get("/dead-stock")
def get_dead_stock_report(
    days: int = Query(default=90, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    cutoff = datetime.utcnow() - timedelta(days=days)

    recently_sold_products = (
        db.query(SalesOrderItem.product_id)
        .join(
            SalesOrder,
            SalesOrder.id == SalesOrderItem.sales_order_id,
        )
        .filter(
            SalesOrder.status.in_(["Dispatched", "Delivered"]),
            SalesOrder.dispatched_at >= cutoff,
        )
        .distinct()
        .subquery()
    )

    rows = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            ~Product.id.in_(
                db.query(recently_sold_products.c.product_id)
            ),
        )
        .order_by(Product.name)
        .all()
    )

    results = []

    for product in rows:
        total_quantity = (
            db.query(
                func.coalesce(
                    func.sum(Inventory.quantity_on_hand), 0
                )
            )
            .filter(Inventory.product_id == product.id)
            .scalar()
            or 0
        )

        last_sold_at = (
            db.query(func.max(SalesOrder.dispatched_at))
            .join(
                SalesOrderItem,
                SalesOrderItem.sales_order_id == SalesOrder.id,
            )
            .filter(
                SalesOrderItem.product_id == product.id,
                SalesOrder.status.in_(["Dispatched", "Delivered"]),
            )
            .scalar()
        )

        results.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "quantity_on_hand": total_quantity,
                "cost_price": format_money(product.cost_price),
                "days_without_sale": days,
                "last_sold_at": (
                    last_sold_at.isoformat()
                    if last_sold_at
                    else None
                ),
            }
        )

    return results


@router.get("/supplier-performance")
def get_supplier_performance_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_admin_or_inventory_manager
    ),
):
    suppliers = (
        db.query(Supplier)
        .filter(Supplier.is_active.is_(True))
        .order_by(Supplier.name)
        .all()
    )

    results = []

    for supplier in suppliers:
        orders = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.supplier_id == supplier.id,
                PurchaseOrder.status == "Received",
            )
            .all()
        )

        eligible_orders = [
            order
            for order in orders
            if order.expected_delivery_date is not None
            and order.received_at is not None
        ]

        on_time_orders = sum(
            1
            for order in eligible_orders
            if order.received_at.date()
            <= order.expected_delivery_date
        )

        late_orders = len(eligible_orders) - on_time_orders

        on_time_percentage = (
            round(on_time_orders / len(eligible_orders) * 100, 2)
            if eligible_orders
            else None
        )

        results.append(
            {
                "supplier_id": supplier.id,
                "supplier_code": supplier.supplier_code,
                "supplier_name": supplier.name,
                "received_purchase_orders": len(orders),
                "eligible_orders": len(eligible_orders),
                "on_time_deliveries": on_time_orders,
                "late_deliveries": late_orders,
                "on_time_delivery_percentage": on_time_percentage,
            }
        )

    return results
