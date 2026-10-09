from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    warehouse_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    manager = relationship(
        "User",
        foreign_keys=[manager_id],
        lazy="selectin",
    )

    inventory = relationship(
        "Inventory",
        back_populates="warehouse",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    purchase_orders = relationship(
        "PurchaseOrder",
        back_populates="warehouse",
        lazy="selectin",
    )

    sales_orders = relationship(
        "SalesOrder",
        back_populates="warehouse",
        lazy="selectin",
    )