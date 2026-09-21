from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PlanRoute(Base):
    """Построенный маршрут бригады в плане: линия, участки и пробег (db/init/042).

    Маршрутизатор на большом дне отвечает минутами, поэтому маршрут строится один раз при
    расчёте, а при открытии плана берётся отсюда. fingerprint — по чему он строился.
    """

    __tablename__ = "plan_route"

    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plan.id", ondelete="CASCADE"), primary_key=True
    )
    engineer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("engineer.id", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(Text)
    travel: Mapped[dict] = mapped_column(JSONB)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
