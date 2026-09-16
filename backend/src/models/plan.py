import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Enum, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PlanRunType(str, enum.Enum):
    BASELINE = "baseline"
    OPTIMIZED = "optimized"
    REPLANNED = "replanned"


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_type: Mapped[PlanRunType] = mapped_column(
        Enum(
            PlanRunType,
            name="plan_run_type",
            create_type=False,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # день, на который построен план (по московскому времени)
    plan_date: Mapped[date | None] = mapped_column(Date)
    # чем посчитан план
    solver: Mapped[str | None] = mapped_column(Text)

    # Одинаковый UUID связывает baseline и оптимизированный план одного запуска.
    comparison_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    solve_duration_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    # общий пробег по дорогам, считается при построении плана
    total_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    # valhalla, haversine или mixed; у старых планов и плана без маршрутов — NULL
    distance_provider: Mapped[str | None] = mapped_column(Text)
