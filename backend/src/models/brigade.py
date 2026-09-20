from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Brigade(Base):
    """Бригада офиса — постоянный состав; её смена на день — строка engineer (030)."""

    __tablename__ = "brigade"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    office_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("office.id"))
    name: Mapped[str] = mapped_column(Text)
    # телефон для звонка оператора, когда бригада выбилась из плана (037)
    phone: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
