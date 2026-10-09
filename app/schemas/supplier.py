
from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    phone: str = Field(pattern=r"^\d{10}$")
    gst_number: str = Field(
        min_length=15,
        max_length=15,
        pattern=r"^[0-9A-Z]{15}$",
    )
    address: str = Field(min_length=1, max_length=500)
    lead_time_days: int = Field(default=0, ge=0)


class SupplierCreate(SupplierBase):
    is_active: bool = True


class SupplierUpdate(BaseModel):
    supplier_code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    phone: str | None = Field(default=None, pattern=r"^\d{10}$")
    gst_number: str | None = Field(
        default=None,
        min_length=15,
        max_length=15,
        pattern=r"^[0-9A-Z]{15}$",
    )
    address: str | None = Field(default=None, min_length=1, max_length=500)
    lead_time_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SupplierResponse(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
