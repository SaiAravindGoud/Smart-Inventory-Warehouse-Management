from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class SalesReturnItem(TimestampMixin, Base):
    __tablename__ = "sales_return_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    sales_return_id: Mapped[int] = mapped_column(
        ForeignKey("sales_returns.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    condition: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Good",
    )

    sales_return = relationship(
        "SalesReturn",
        back_populates="items",
        lazy="selectin",
    )

    product = relationship(
        "Product",
        lazy="selectin",
    )