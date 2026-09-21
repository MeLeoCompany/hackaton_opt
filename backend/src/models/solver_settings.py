from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SolverSettings(Base):
    """Параметры расчёта, которые оператор меняет из интерфейса (db/init/040).

    У cuOpt настраивается только время поиска: чем больше лимит, тем лучше маршруты.
    Остальное — вес пробега, попытки сверки плана ОТ с расписанием и подробный лог решателя.
    """

    __tablename__ = "solver_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    time_limit_seconds: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    seconds_per_location: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    max_time_limit_seconds: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    free_locations: Mapped[int] = mapped_column(SmallInteger)
    distance_weight: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    transit_attempts: Mapped[int] = mapped_column(SmallInteger)
    verbose_log: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
