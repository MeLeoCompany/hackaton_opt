from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.reference import Priority, Skill, Transport


class Request(Base):
    __tablename__ = "request"
    __table_args__ = (CheckConstraint("window_end > window_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    address: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    priority_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("priority.id"))
    skill_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("skill.id"))
    transport_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("transport.id"))

    priority: Mapped["Priority"] = relationship()
    skill: Mapped["Skill"] = relationship()
    transport: Mapped["Transport | None"] = relationship()
