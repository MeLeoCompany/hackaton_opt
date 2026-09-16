from sqlalchemy import ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class Transport(Base):
    __tablename__ = "transport"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class Priority(Base):
    __tablename__ = "priority"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class WorkType(Base):
    """Тип работ с нормативами времени из ТЗ.

    work_minutes — работа на месте: технические работы и документы сложены вместе.
    travel_minutes — норматив дороги до клиента/ТКД; в плане дорога считается по Valhalla,
    норматив остаётся справочной величиной.
    """

    __tablename__ = "work_type"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    skill_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("skill.id"))
    travel_minutes: Mapped[int] = mapped_column(Integer)
    work_minutes: Mapped[int] = mapped_column(Integer)
    baseline_minutes: Mapped[int] = mapped_column(Integer)
