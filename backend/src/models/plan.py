import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Enum, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
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

    # время работы решателя без загрузки матриц и расчёта геометрии
    solve_duration_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    # строгий порядок критериев, с которым был рассчитан план
    objective_policy: Mapped[dict | None] = mapped_column(JSONB)

    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    # общий пробег по дорогам, считается при построении плана
    total_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    # valhalla, haversine или mixed; у старых планов и плана без маршрутов — NULL
    distance_provider: Mapped[str | None] = mapped_column(Text)
    # когда план утверждён; NULL — черновик. Утверждённый план на день только один:
    # его заявки закрепляются за ним и в планы других дней не попадают
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
