"""Справочник бригад. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AppUser, Brigade, Engineer


async def list_brigades(
    session: AsyncSession, office_id: int
) -> list[tuple[Brigade, AppUser | None, int]]:
    """Бригады офиса с учёткой для приложения и числом заведённых смен."""
    shifts = (
        select(Engineer.brigade_id, func.count().label("shifts"))
        .group_by(Engineer.brigade_id)
        .subquery()
    )
    result = await session.execute(
        select(Brigade, AppUser, func.coalesce(shifts.c.shifts, 0))
        .outerjoin(AppUser, AppUser.brigade_id == Brigade.id)
        .outerjoin(shifts, shifts.c.brigade_id == Brigade.id)
        .where(Brigade.office_id == office_id)
        .order_by(Brigade.name)
    )
    return [(brigade, account, count) for brigade, account, count in result.all()]


async def get_brigade(session: AsyncSession, brigade_id: int) -> Brigade | None:
    return await session.get(Brigade, brigade_id)


async def find_by_name(session: AsyncSession, office_id: int, name: str) -> Brigade | None:
    result = await session.execute(
        select(Brigade).where(Brigade.office_id == office_id, Brigade.name == name)
    )
    return result.scalar_one_or_none()


async def get_account(session: AsyncSession, brigade_id: int) -> AppUser | None:
    result = await session.execute(select(AppUser).where(AppUser.brigade_id == brigade_id))
    return result.scalar_one_or_none()


async def count_shifts(session: AsyncSession, brigade_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Engineer).where(Engineer.brigade_id == brigade_id)
    )
    return int(result.scalar_one())


def add_brigade(session: AsyncSession, fields: dict) -> Brigade:
    brigade = Brigade(**fields)
    session.add(brigade)
    return brigade


async def rename_shifts(session: AsyncSession, brigade_id: int, name: str) -> None:
    """Смены бригады хранят копию её названия — переименовали бригаду, переименовываем и их."""
    await session.execute(
        update(Engineer)
        .where(Engineer.brigade_id == brigade_id)
        .values(name=name)
        .execution_options(synchronize_session=False)
    )


async def delete_brigade(session: AsyncSession, brigade: Brigade) -> None:
    await session.delete(brigade)
