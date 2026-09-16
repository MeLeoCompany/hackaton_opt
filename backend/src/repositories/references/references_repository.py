"""Чтение справочников из БД."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Priority, Skill, Transport, WorkType


async def list_skills(session: AsyncSession) -> list[Skill]:
    result = await session.execute(select(Skill).order_by(Skill.id))
    return list(result.scalars().all())


async def list_priorities(session: AsyncSession) -> list[Priority]:
    result = await session.execute(select(Priority).order_by(Priority.id))
    return list(result.scalars().all())


async def list_transports(session: AsyncSession) -> list[Transport]:
    result = await session.execute(select(Transport).order_by(Transport.id))
    return list(result.scalars().all())


async def list_work_types(session: AsyncSession) -> list[WorkType]:
    result = await session.execute(select(WorkType).order_by(WorkType.id))
    return list(result.scalars().all())
