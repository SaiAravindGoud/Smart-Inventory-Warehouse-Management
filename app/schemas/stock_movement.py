from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    movement_type: str
    quantity: int
    reference_id: int | None
    balance_after: int
    unit_cost: Decimal | None
    performed_by: int | None
    created_at: datetime