"""Чтение и запись исполнителей в БД. Коммит делает сервис — здесь только запросы.

Навыки исполнителя загружаются сразу вместе с ним (selectinload): в асинхронной сессии
«догрузить потом» при обращении к engineer.skills нельзя.
"""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Assignment, Engineer, Event, Skill


async def list_engineers(session: AsyncSession) -> list[Engineer]:
    result = await session.execute(select(Engineer).options(selectinload(Engineer.skills)).order_by(Engineer.id))
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


async def sync_engineer_id_sequence(session: AsyncSession) -> None:
    """Сдвигает автонумерацию исполнителей за самый большой номер в таблице.

    Нужно после вставки исполнителя с явным номером: иначе следующий исполнитель без номера
    получит из автонумерации номер, который уже занят.
    """
    await session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('engineer', 'id'), "
            "GREATEST((SELECT MAX(id) FROM engineer), 1))"
        )
    )
