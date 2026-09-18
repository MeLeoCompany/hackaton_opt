from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.reference import Priority, Skill, Transport, WorkType


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
    # какое оборудование нужно для заявки; None — не нужно
    equipment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("equipment.id"))
    # выключенная заявка хранится, но в сборку задачи планирования не попадает
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    priority: Mapped["Priority"] = relationship()
    skill: Mapped["Skill"] = relationship()
    transport: Mapped["Transport | None"] = relationship()
    work_type: Mapped["WorkType | None"] = relationship()
