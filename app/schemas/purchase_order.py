
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity_ordered: int = Field(gt=0)
    unit_cost: Decimal = Field(gt=0, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    expected_delivery_date: date | None = None
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    po_number: str
    supplier_id: int
    warehouse_id: int
    expected_delivery_date: date | None
    received_at: datetime | None
    total_amount: Decimal
    status: str
    items: list[PurchaseOrderItemResponse]


class PurchaseOrderReceiveItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity_received: int = Field(gt=0)


class PurchaseOrderReceive(BaseModel):
    items: list[PurchaseOrderReceiveItem] = Field(min_length=1)


class PurchaseOrderStatusResponse(BaseModel):
    id: int
    po_number: str
    status: str
    received_at: datetime | None = None
    total_amount: Decimal
    message: str | None = None
