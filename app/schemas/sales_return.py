from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SalesReturnItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    condition: str = Field(
        default="Good",
        pattern="^(Good|Damaged)$",
    )


class SalesReturnCreate(BaseModel):
    sales_order_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    items: list[SalesReturnItemCreate] = Field(min_length=1)


class SalesReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    condition: str


class SalesReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sales_order_id: int
    reason: str
    status: str
    refund_amount: Decimal
    rejection_reason: str | None
    items: list[SalesReturnItemResponse]


class ReturnInspectionItem(BaseModel):
    product_id: int = Field(gt=0)
    condition: str = Field(
        pattern="^(Good|Damaged)$",
    )


class ReturnInspection(BaseModel):
    items: list[ReturnInspectionItem] = Field(min_length=1)


class ReturnReject(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=500)


class ReturnStatusResponse(BaseModel):
    id: int
    sales_order_id: int
    status: str
    refund_amount: Decimal
    rejection_reason: str | None = None