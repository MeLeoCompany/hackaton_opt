import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, func
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
        Enum(PlanRunType, name="plan_run_type", create_type=False, values_callable=lambda cls: [e.value for e in cls])
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
