from app.schemas.audit_log import AuditLogResponse
from app.schemas.auth import (
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from app.schemas.common import (
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)
from app.schemas.inventory import (
    InventoryDetailResponse,
    InventoryResponse,
    StockMovementResponse,
)
from app.schemas.product import (
    ProductCreate,
    ProductInventoryResponse,
    ProductResponse,
    ProductUpdate,
)
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderItemResponse,
    PurchaseOrderReceive,
    PurchaseOrderReceiveItem,
    PurchaseOrderResponse,
    PurchaseOrderStatusResponse,
)
from app.schemas.sales_order import (
    SalesOrderCreate,
    SalesOrderDispatch,
    SalesOrderItemCreate,
    SalesOrderItemResponse,
    SalesOrderResponse,
    SalesOrderStatusResponse,
)
from app.schemas.sales_return import (
    ReturnInspection,
    ReturnInspectionItem,
    ReturnReject,
    ReturnStatusResponse,
    SalesReturnCreate,
    SalesReturnItemCreate,
    SalesReturnItemResponse,
    SalesReturnResponse,
)
from app.schemas.stock_movement import StockMovementResponse
from app.schemas.supplier import (
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from app.schemas.warehouse import (
    InventorySummary,
    WarehouseCreate,
    WarehouseInventoryResponse,
    WarehouseResponse,
    WarehouseUpdate,
)