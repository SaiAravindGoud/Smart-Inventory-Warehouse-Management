
from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.category import router as category_router
from app.routers.product import router as product_router
from app.routers.warehouse import router as warehouse_router
from app.routers.inventory import router as inventory_router
from app.routers.supplier import router as supplier_router
from app.routers.purchase_order import router as purchase_order_router
from app.routers.customer import router as customer_router
from app.routers.sales_order import router as sales_order_router
from app.routers.sales_return import router as sales_return_router
from app.routers.audit_log import router as audit_log_router
from app.routers.report import router as report_router

app = FastAPI(
    title="Smart Inventory & Warehouse Management System",
    version="1.0.0",
    description="Inventory and Warehouse Management API",
)


@app.get("/")
def root():
    return {
        "message": "Smart Inventory & Warehouse Management System is running"
    }


app.include_router(auth_router)
app.include_router(category_router)
app.include_router(product_router)
app.include_router(warehouse_router)
app.include_router(inventory_router)
app.include_router(supplier_router)
app.include_router(purchase_order_router)
app.include_router(customer_router)
app.include_router(sales_order_router)
app.include_router(sales_return_router)
app.include_router(audit_log_router)
app.include_router(report_router)
