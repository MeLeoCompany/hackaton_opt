"""Чтение и запись учёток. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AppUser, UserRole


async def list_users(session: AsyncSession) -> list[AppUser]:
    """Учётки администраторов и диспетчеров; учётки бригад — в справочнике бригад."""
    result = await session.execute(
        select(AppUser).where(AppUser.role != UserRole.BRIGADE.value).order_by(AppUser.id)
    )
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: int) -> AppUser | None:
    return await session.get(AppUser, user_id)


async def find_user_by_login(session: AsyncSession, login: str) -> AppUser | None:
    result = await session.execute(
        select(AppUser).where(func.lower(AppUser.login) == login.lower())
    )
    return result.scalar_one_or_none()


async def count_active_admins(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(AppUser)
        .where(AppUser.role == UserRole.ADMIN.value, AppUser.is_active.is_(True))
    )
    return int(count or 0)


def add_user(session: AsyncSession, fields: dict) -> AppUser:
    user = AppUser(**fields)
    session.add(user)
    return user


def apply_changes(user: AppUser, fields: dict) -> None:
    for field_name, value in fields.items():
        setattr(user, field_name, value)


async def delete_user(session: AsyncSession, user: AppUser) -> None:
    await session.delete(user)
