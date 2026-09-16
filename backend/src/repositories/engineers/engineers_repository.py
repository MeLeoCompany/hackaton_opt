"""Чтение и запись исполнителей в БД. Коммит делает сервис — здесь только запросы.

Навыки исполнителя загружаются сразу вместе с ним (selectinload): в асинхронной сессии
«догрузить потом» при обращении к engineer.skills нельзя.
"""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Assignment, Engineer, Event, Skill

ENGINEER_ID_LOCK_KEY = 7419822


async def list_engineers(session: AsyncSession) -> list[Engineer]:
    result = await session.execute(select(Engineer).options(selectinload(Engineer.skills)).order_by(Engineer.input_order))
    return list(result.scalars().all())


async def list_engineers_in_period(
    session: AsyncSession, period_start: datetime, period_end: datetime
) -> list[Engineer]:
    """Исполнители, смена которых пересекается с периодом [period_start, period_end)."""
    result = await session.execute(
        select(Engineer)
        .options(selectinload(Engineer.skills))
        .where(Engineer.shift_start < period_end, Engineer.shift_end > period_start)
        .order_by(Engineer.input_order)
    )
    return list(result.scalars().all())


async def get_engineer(session: AsyncSession, engineer_id: int) -> Engineer | None:
    result = await session.execute(
        select(Engineer).options(selectinload(Engineer.skills)).where(Engineer.id == engineer_id)
    )
    return result.scalar_one_or_none()


async def get_skills_by_ids(session: AsyncSession, skill_ids: list[int]) -> list[Skill]:
    result = await session.execute(select(Skill).where(Skill.id.in_(skill_ids)).order_by(Skill.id))
    return list(result.scalars().all())


def add_engineer(session: AsyncSession, fields: dict, skills: list[Skill]) -> Engineer:
    engineer = Engineer(**fields)
    engineer.skills = skills
    session.add(engineer)
    return engineer


def apply_changes(engineer: Engineer, fields: dict, skills: list[Skill]) -> None:
    for field_name, value in fields.items():
        setattr(engineer, field_name, value)
    engineer.skills = skills


async def delete_engineer(session: AsyncSession, engineer: Engineer) -> None:
    await session.delete(engineer)


async def count_engineer_usages(session: AsyncSession, engineer_id: int) -> tuple[int, int]:
    """Сколько раз исполнитель встречается в назначениях планов и в событиях перепланирования."""
    assignments = await session.scalar(
        select(func.count()).select_from(Assignment).where(Assignment.engineer_id == engineer_id)
    )
    events = await session.scalar(
        select(func.count()).select_from(Event).where(Event.engineer_id == engineer_id)
    )
    return int(assignments or 0), int(events or 0)


async def list_engineer_ids(session: AsyncSession) -> set[int]:
    """Номера всех исполнителей — из них выбирается номер для нового."""
    result = await session.execute(select(Engineer.id))
    return set(result.scalars().all())


async def lock_engineer_ids(session: AsyncSession) -> None:
    """Serialize explicit and automatic engineer IDs until commit/rollback."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": ENGINEER_ID_LOCK_KEY}
    )
