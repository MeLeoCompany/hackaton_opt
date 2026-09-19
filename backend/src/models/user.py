import enum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"  # справочники, пользователи, любой офис
    DISPATCHER = "dispatcher"  # только свой офис
    BRIGADE = "brigade"  # мобильное приложение: свой маршрут и отметки по заявкам


class AppUser(Base):
    """Учётка администратора, диспетчера офиса или бригады (018, 028 в db/init)."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    login: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    office_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("office.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # учётка бригады: вход в мобильное приложение этой бригады (справочник бригад, 030)
    brigade_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("brigade.id"))
