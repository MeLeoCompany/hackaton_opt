from sqlalchemy import BigInteger, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Equipment(Base):
    """Тип оборудования, которое техник привозит на заявку (db/init/017_equipment.sql)."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class TransportEquipmentCapacity(Base):
    """Сколько штук этого оборудования увозит бригада на этом транспорте (db/init/051).

    Предел выдачи: в машину влезет тридцать роутеров, пешеход столько не унесёт.
    """

    __tablename__ = "transport_equipment_capacity"

    transport_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("transport.id", ondelete="CASCADE"), primary_key=True
    )
    equipment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True
    )
    max_quantity: Mapped[int] = mapped_column(Integer)
