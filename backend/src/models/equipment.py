from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Equipment(Base):
    """Тип оборудования, которое техник привозит на заявку (db/init/017_equipment.sql)."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
