import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class RequestStatusId(int, enum.Enum):
    """Номера статусов из db/init/022_request_status.sql: на них ссылается код."""

    NEW = 1  # Новая — ждёт планирования
    PLANNED = 2  # В плане — закреплена за утверждённым планом
    DONE = 3  # Выполнена — отмечена оператором
    CANCELLED = 4  # Отменена
    IN_PROGRESS = 5  # В работе — бригада на месте, идут работы; в пересчёт не идёт
    EN_ROUTE = 6  # В пути — бригада выехала на заявку; в пересчёт не идёт (031)


class RequestStatus(Base):
    __tablename__ = "request_status"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    # заявка в этом статусе попадает в расчёт плана
    plannable: Mapped[bool] = mapped_column(Boolean)


class RequestStatusTransition(Base):
    """Допустимый переход статуса. manual — делает оператор; иначе — система."""

    __tablename__ = "request_status_transition"

    from_status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("request_status.id"), primary_key=True
    )
    to_status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("request_status.id"), primary_key=True
    )
    manual: Mapped[bool] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(Text)


class RequestStatusHistory(Base):
    """Смена статуса заявки: кто, когда, вручную или системой, по какому плану (db/init/023)."""

    __tablename__ = "request_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("request.id", ondelete="CASCADE")
    )
    # None — заявка появилась
    from_status_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("request_status.id")
    )
    to_status_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("request_status.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    manual: Mapped[bool] = mapped_column(Boolean)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
