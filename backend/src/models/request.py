from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.reference import Priority, Skill, Transport, WorkType
from src.models.request_status import RequestStatus


class RequestEquipment(Base):
    """Сколько штук оборудования одного типа нужно на заявку (db/init/019, 021)."""

    __tablename__ = "request_equipment"

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("request.id", ondelete="CASCADE"), primary_key=True
    )
    equipment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("equipment.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)


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
    # статус заявки: новая, в плане, выполнена, отменена (db/init/022_request_status.sql)
    status_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("request_status.id"))

    priority: Mapped["Priority"] = relationship()
    skill: Mapped["Skill"] = relationship()
    transport: Mapped["Transport | None"] = relationship()
    work_type: Mapped["WorkType | None"] = relationship()
    # статус грузится сразу с заявкой: из него видно, идёт ли она в планирование
    status: Mapped["RequestStatus"] = relationship(lazy="selectin")
    # требуемое оборудование грузится сразу вместе с заявкой: в асинхронной сессии
    # «догрузить потом» при обращении к полю нельзя
    equipment: Mapped[list["RequestEquipment"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="RequestEquipment.equipment_id"
    )

    @property
    def is_active(self) -> bool:
        """Попадает ли заявка в планирование — по её статусу (раньше это был флаг)."""
        return self.status.plannable
