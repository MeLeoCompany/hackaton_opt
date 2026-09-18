from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class DaySync(Base):
    """До какого времени статусы заявок дня офиса синхронизированы с утверждённым планом."""

    __tablename__ = "day_sync"

    office_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("office.id"), primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date, primary_key=True)
    synced_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
