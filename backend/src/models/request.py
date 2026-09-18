from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Table,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.equipment import Equipment
from src.models.reference import Priority, Skill, Transport, WorkType

# какое оборудование нужно привезти на заявку (db/init/019_request_equipment_list.sql)
request_equipment = Table(
    "request_equipment",
    Base.metadata,
    Column(
        "request_id", BigInteger, ForeignKey("request.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("equipment_id", BigInteger, ForeignKey("equipment.id"), primary_key=True),
)


class Request(Base):
    __tablename__ = "request"
    __table_args__ = (CheckConstraint("window_end > window_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    input_order: Mapped[int] = mapped_column(BigInteger, server_default=FetchedValue())
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    address: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    priority_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("priority.id"))
    skill_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("skill.id"))
    transport_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("transport.id"))
    # тип работ из справочника нормативов: из него берутся длительность и навык по умолчанию
    work_type_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("work_type.id"))
    # заявка закреплена за утверждённым планом: другие дни её не берут (окна через полночь)
    approved_plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan.id"))
    # чья заявка: её видит и планирует только этот офис
    office_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("office.id"))
    # выключенная заявка хранится, но в сборку задачи планирования не попадает
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    priority: Mapped["Priority"] = relationship()
    skill: Mapped["Skill"] = relationship()
    transport: Mapped["Transport | None"] = relationship()
    work_type: Mapped["WorkType | None"] = relationship()
    # оборудование грузится сразу вместе с заявкой: в асинхронной сессии «догрузить потом»
    # при обращении к полю нельзя
    equipment: Mapped[list["Equipment"]] = relationship(
        secondary=request_equipment, lazy="selectin", order_by="Equipment.id"
    )

    @property
    def equipment_ids(self) -> list[int]:
        return [item.id for item in self.equipment]
