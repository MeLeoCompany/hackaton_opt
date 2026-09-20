"""Чтение журнала расчётов: запуски офиса и ход каждого (db/init/038)."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.models import AppUser, PlanRun, PlanRunEvent


async def list_runs(
    session: AsyncSession, *, office_id: int, limit: int = 50
) -> list[tuple[PlanRun, str | None]]:
    """Запуски офиса, новые первыми, с именем того, кто их запустил."""
    result = await session.execute(
        select(PlanRun, AppUser.name)
        .outerjoin(AppUser, AppUser.id == PlanRun.user_id)
        .where(PlanRun.office_id == office_id)
        .order_by(PlanRun.started_at.desc())
        .limit(limit)
    )
    return [(run, user_name) for run, user_name in result.all()]


async def get_run(
    session: AsyncSession, run_id: uuid.UUID, *, office_id: int
) -> tuple[PlanRun, str | None] | None:
    result = await session.execute(
        select(PlanRun, AppUser.name)
        .outerjoin(AppUser, AppUser.id == PlanRun.user_id)
        .where(PlanRun.id == run_id, PlanRun.office_id == office_id)
    )
    return result.first()


async def list_events(session: AsyncSession, run_id: uuid.UUID) -> list[PlanRunEvent]:
    result = await session.execute(
        select(PlanRunEvent).where(PlanRunEvent.run_id == run_id).order_by(PlanRunEvent.id)
    )
    return list(result.scalars().all())


async def request_cancel(session: AsyncSession, run_id: uuid.UUID, *, user_id: int | None) -> None:
    """Ставит флаг «Прервать» и пишет об этом в журнал: видно, кто остановил расчёт."""
    await session.execute(
        update(PlanRun).where(PlanRun.id == run_id).values(cancel_requested=True)
    )
    session.add(
        PlanRunEvent(
            run_id=run_id,
            at=clock.now(),
            level="warning",
            source="operator",
            step="",
            message="Оператор нажал «Прервать расчёт»",
        )
    )
