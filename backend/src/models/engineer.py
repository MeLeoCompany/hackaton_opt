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
    Numeric,
    SmallInteger,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.models.reference import Skill, Transport

engineer_skill = Table(
    "engineer_skill",
    Base.metadata,
    Column(
        "engineer_id", BigInteger, ForeignKey("engineer.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("skill_id", SmallInteger, ForeignKey("skill.id"), primary_key=True),
)


class Engineer(Base):
    __tablename__ = "engineer"
    __table_args__ = (CheckConstraint("shift_end > shift_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    input_order: Mapped[int] = mapped_column(BigInteger, server_default=FetchedValue())
    name: Mapped[str] = mapped_column(Text)
    start_latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    start_longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    shift_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shift_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transport_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("transport.id"))
    # чья бригада; с другими офисами она не работает
    office_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("office.id"))
    # выезжает из своего офиса: старт = точка офиса, иначе — своя точка
    start_at_office: Mapped[bool] = mapped_column(Boolean, default=False)

    transport: Mapped["Transport"] = relationship()
    skills: Mapped[list["Skill"]] = relationship(secondary=engineer_skill)
