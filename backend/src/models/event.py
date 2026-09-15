import enum
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.engineer import Engineer
from src.models.request import Request


class EventType(str, enum.Enum):
    URGENT_REQUEST = "urgent_request"
    REQUEST_CANCELLATION = "request_cancellation"
    ENGINEER_UNAVAILABILITY = "engineer_unavailability"


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "(event_type = 'engineer_unavailability' AND engineer_id IS NOT NULL AND request_id IS NULL) "
            "OR (event_type IN ('urgent_request', 'request_cancellation') "
            "AND request_id IS NOT NULL AND engineer_id IS NULL)"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type", create_type=False, values_callable=lambda cls: [e.value for e in cls])
    )
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("request.id"))
    engineer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("engineer.id"))

    request: Mapped["Request | None"] = relationship()
    engineer: Mapped["Engineer | None"] = relationship()
