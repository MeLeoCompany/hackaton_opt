"""Чтение и запись офисов в БД. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AppUser, Engineer, Office, Plan, Request


async def list_offices(session: AsyncSession) -> list[tuple[Office, int]]:
    """Офисы по номеру вместе с числом бригад офиса."""
    engineer_count = (
        select(func.count())
        .select_from(Engineer)
        .where(Engineer.office_id == Office.id)
        .scalar_subquery()
    )
    result = await session.execute(select(Office, engineer_count).order_by(Office.id))
    return [(office, int(count)) for office, count in result.all()]


async def get_office(session: AsyncSession, office_id: int) -> Office | None:
    return await session.get(Office, office_id)


async def find_office_by_name(session: AsyncSession, name: str) -> Office | None:
    result = await session.execute(select(Office).where(func.lower(Office.name) == name.lower()))
    return result.scalar_one_or_none()


async def count_engineers(session: AsyncSession, office_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Engineer).where(Engineer.office_id == office_id)
    )
    return int(count or 0)


def add_office(session: AsyncSession, fields: dict) -> Office:
    office = Office(**fields)
    session.add(office)
    return office


def apply_changes(office: Office, fields: dict) -> None:
    for field_name, value in fields.items():
        setattr(office, field_name, value)


async def move_engineers_to_office(session: AsyncSession, office: Office) -> None:
    """Старт бригад, выезжающих из офиса, -> координаты офиса: офис переехал — и они с ним."""
    await session.execute(
        update(Engineer)
        .where(Engineer.office_id == office.id, Engineer.start_at_office.is_(True))
        .values(start_latitude=office.latitude, start_longitude=office.longitude)
    )


async def count_usages(session: AsyncSession, office_id: int) -> dict[str, int]:
    """Сколько данных офиса: пока они есть, офис не удалить."""
    counts = {}
    for label, model in (
        ("заявок", Request),
        ("бригад", Engineer),
        ("планов", Plan),
        ("учёток", AppUser),
    ):
        counts[label] = int(
            await session.scalar(
                select(func.count()).select_from(model).where(model.office_id == office_id)
            )
            or 0
        )
    return counts


async def delete_office(session: AsyncSession, office: Office) -> None:
    await session.delete(office)
