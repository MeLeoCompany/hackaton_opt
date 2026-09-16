from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.engineer import Engineer
from src.models.plan import Plan
from src.models.request import Request


class Assignment(Base):
    __tablename__ = "assignment"
    __table_args__ = (
        UniqueConstraint("plan_id", "request_id"),
        CheckConstraint(
            "(engineer_id IS NULL AND visit_order IS NULL AND planned_arrival_time IS NULL) "
            "OR (engineer_id IS NOT NULL AND visit_order IS NOT NULL AND planned_arrival_time IS NOT NULL)"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.id", ondelete="CASCADE"))
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("request.id"))
    engineer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("engineer.id"))
    visit_order: Mapped[int | None] = mapped_column(Integer)
    planned_arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unassigned_reason: Mapped[str | None] = mapped_column(Text)

    plan: Mapped["Plan"] = relationship()
    request: Mapped["Request"] = relationship()
    engineer: Mapped["Engineer | None"] = relationship()
