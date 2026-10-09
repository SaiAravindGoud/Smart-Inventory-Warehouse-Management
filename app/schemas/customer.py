from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CustomerBase(BaseModel):
    customer_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    phone: str = Field(pattern=r"^\d{10}$")
    address: str = Field(min_length=1, max_length=500)
    credit_limit: Decimal = Field(default=Decimal("0.00"), ge=0)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    phone: str | None = Field(default=None, pattern=r"^\d{10}$")
    address: str | None = Field(default=None, min_length=1, max_length=500)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool