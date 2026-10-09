from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SalesOrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class SalesOrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    items: list[SalesOrderItemCreate] = Field(min_length=1)


class SalesOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class SalesOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    so_number: str
    customer_id: int
    warehouse_id: int
    subtotal: Decimal
    tax_amount: Decimal
    grand_total: Decimal
    status: str
    courier_name: str | None
    tracking_number: str | None
    dispatched_at: datetime | None
    delivered_at: datetime | None
    items: list[SalesOrderItemResponse]


class SalesOrderDispatch(BaseModel):
    courier_name: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(min_length=1, max_length=100)


class SalesOrderStatusResponse(BaseModel):
    id: int
    so_number: str
    status: str
    courier_name: str | None = None
    tracking_number: str | None = None
    dispatched_at: datetime | None = None
    delivered_at: datetime | None = None