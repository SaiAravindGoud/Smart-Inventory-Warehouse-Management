
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    sku: str = Field(min_length=1, max_length=100)
    barcode: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int = Field(gt=0)
    unit: str = Field(default="Piece", pattern="^(Piece|Box|Kg|Litre)$")
    cost_price: Decimal = Field(gt=0, decimal_places=2)
    selling_price: Decimal = Field(gt=0, decimal_places=2)
    reorder_level: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)
    preferred_supplier_id: int | None = Field(default=None, gt=0)


class ProductCreate(ProductBase):
    is_active: bool = True

    @model_validator(mode="after")
    def validate_prices(self):
        if self.selling_price < self.cost_price:
            raise ValueError(
                "selling_price must be greater than or equal to cost_price"
            )
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    barcode: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int | None = Field(default=None, gt=0)
    unit: str | None = Field(
        default=None,
        pattern="^(Piece|Box|Kg|Litre)$",
    )
    cost_price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    selling_price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    reorder_level: int | None = Field(default=None, ge=0)
    reorder_quantity: int | None = Field(default=None, ge=0)
    preferred_supplier_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_prices(self):
        if (
            self.cost_price is not None
            and self.selling_price is not None
            and self.selling_price < self.cost_price
        ):
            raise ValueError(
                "selling_price must be greater than or equal to cost_price"
            )
        return self


class ProductInventoryResponse(BaseModel):
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    inventory: list[ProductInventoryResponse] = []
    total_stock: int = 0
