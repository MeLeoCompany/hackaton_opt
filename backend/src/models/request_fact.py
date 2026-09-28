from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class RequestFact(Base):
    """Что бригада отметила по заявке в мобильном приложении: выехала, прибыла, закончила."""

    __tablename__ = "request_fact"

    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("request.id", ondelete="CASCADE"), primary_key=True
    )
    engineer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("engineer.id"))
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # когда бригада закончит эту заявку — со слов оператора (050). Спрашивается один раз:
    # следующий пересчёт берёт то же время, пока оно не прошло
    expected_free_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
