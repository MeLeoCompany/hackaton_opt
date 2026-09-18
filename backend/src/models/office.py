from decimal import Decimal

from sqlalchemy import BigInteger, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Office(Base):
    """Офис, из которого исполнители выезжают на смену (db/init/016_office.sql)."""

    __tablename__ = "office"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    address: Mapped[str] = mapped_column(Text)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
