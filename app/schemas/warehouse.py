from pydantic import BaseModel, ConfigDict, Field


class WarehouseBase(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=500)
    capacity: int = Field(gt=0)
    manager_id: int | None = Field(default=None, gt=0)


class WarehouseCreate(WarehouseBase):
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    warehouse_code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    capacity: int | None = Field(default=None, gt=0)
    manager_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class WarehouseResponse(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


class InventorySummary(BaseModel):
    product_id: int
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int


class WarehouseInventoryResponse(BaseModel):
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    items: list[InventorySummary]
    total: int
    skip: int
    limit: int
