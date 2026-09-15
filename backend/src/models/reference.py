from sqlalchemy import SmallInteger, Text
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
