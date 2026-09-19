"""Чтение и запись справочника оборудования. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EngineerEquipment, Equipment, RequestEquipment


async def list_equipment(session: AsyncSession) -> list[tuple[Equipment, int, int]]:
    """Типы оборудования по номеру: сколько заявок их требуют и у скольких бригад они есть."""
    request_count = (
        select(func.count())
        .select_from(RequestEquipment)
        .where(RequestEquipment.equipment_id == Equipment.id)
        .scalar_subquery()
    )
    engineer_count = (
        select(func.count())
        .select_from(EngineerEquipment)
        .where(EngineerEquipment.equipment_id == Equipment.id)
        .scalar_subquery()
    )
    result = await session.execute(
        select(Equipment, request_count, engineer_count).order_by(Equipment.id)
    )
    return [
        (equipment, int(requests), int(engineers))
        for equipment, requests, engineers in result.all()
    ]


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
        .select_from(RequestEquipment)
        .where(RequestEquipment.equipment_id == equipment_id)
    )
    return int(count or 0)


def add_equipment(session: AsyncSession, fields: dict) -> Equipment:
    equipment = Equipment(**fields)
    session.add(equipment)
    return equipment


def apply_changes(equipment: Equipment, fields: dict) -> None:
    for field_name, value in fields.items():
        setattr(equipment, field_name, value)


async def count_engineers(session: AsyncSession, equipment_id: int) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(EngineerEquipment)
        .where(EngineerEquipment.equipment_id == equipment_id)
    )
    return int(count or 0)


async def delete_equipment(session: AsyncSession, equipment: Equipment) -> None:
    await session.delete(equipment)
