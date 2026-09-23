from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class TravelCache(Base):
    """Ответ R5 для пары точек и времени суток выезда (db/init/044, docs/algoCachV1.md).

    kind: matrix — пара матрицы для cuOpt, route — поездка по плечу для проверки и карты.
    """

    __tablename__ = "travel_cache"

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    depart_seconds: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_lat: Mapped[Decimal] = mapped_column(Numeric(10, 6), primary_key=True)
    from_lon: Mapped[Decimal] = mapped_column(Numeric(10, 6), primary_key=True)
    to_lat: Mapped[Decimal] = mapped_column(Numeric(10, 6), primary_key=True)
    to_lon: Mapped[Decimal] = mapped_column(Numeric(10, 6), primary_key=True)
    duration_min: Mapped[float | None] = mapped_column(Float)
    route: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TravelCacheState(Base):
    """По какому расписанию GTFS посчитан кеш: сменилось — кеш очищается."""

    __tablename__ = "travel_cache_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    gtfs_fingerprint: Mapped[str | None] = mapped_column(Text)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
