import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PlanRun(Base):
    """Запуск расчёта: что считаем, на каком шаге и чем кончилось (db/init/038)."""

    __tablename__ = "plan_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    office_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("office.id", ondelete="CASCADE"))
    plan_date: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)  # build / replan / preview
    solver: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # running / done / failed
    step: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plan.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    # оператор нажал «Прервать»: расчёт проверяет флаг между шагами и останавливается (039)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanRunEvent(Base):
    """Одна строка хода расчёта: какой шаг, что произошло и когда (db/init/038)."""

    __tablename__ = "plan_run_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_run.id", ondelete="CASCADE")
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(Text, default="info")
    step: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text)
    progress: Mapped[int | None] = mapped_column(SmallInteger)
    # дерево: шаг — узел, внутри него подробности этого шага (039)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plan_run_event.id", ondelete="CASCADE")
    )
    # кто написал строку: planner, cuopt, r5, valhalla, operator
    source: Mapped[str] = mapped_column(Text, default="planner")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSONB)
