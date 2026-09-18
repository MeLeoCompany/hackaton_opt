"""Чтение и запись справочника оборудования. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Equipment, request_equipment


async def list_equipment(session: AsyncSession) -> list[tuple[Equipment, int]]:
    """Типы оборудования по номеру вместе с числом заявок, которые их требуют."""
    request_count = (
        select(func.count())
        .select_from(request_equipment)
        .where(request_equipment.c.equipment_id == Equipment.id)
        .scalar_subquery()
    )
    result = await session.execute(select(Equipment, request_count).order_by(Equipment.id))
    return [(equipment, int(count)) for equipment, count in result.all()]


async def get_equipment(session: AsyncSession, equipment_id: int) -> Equipment | None:
    return await session.get(Equipment, equipment_id)


async def find_equipment_by_name(session: AsyncSession, name: str) -> Equipment | None:
    result = await session.execute(
        select(Equipment).where(func.lower(Equipment.name) == name.lower())
    )
    return result.scalar_one_or_none()


async def count_requests(session: AsyncSession, equipment_id: int) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(request_equipment)
        .where(request_equipment.c.equipment_id == equipment_id)
    )
    return int(count or 0)


def add_equipment(session: AsyncSession, fields: dict) -> Equipment:
    equipment = Equipment(**fields)
    session.add(equipment)
    return equipment


def apply_changes(equipment: Equipment, fields: dict) -> None:
    for field_name, value in fields.items():
        setattr(equipment, field_name, value)


async def delete_equipment(session: AsyncSession, equipment: Equipment) -> None:
    await session.delete(equipment)
