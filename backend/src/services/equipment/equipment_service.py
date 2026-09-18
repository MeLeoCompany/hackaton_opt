"""Оборудование: справочник того, что техник привозит на заявку."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.models import Equipment
from src.repositories.equipment import equipment_repository
from src.schemas.equipment import EquipmentRead, EquipmentWrite


class EquipmentNotFoundError(NotFoundError):
    """Такого типа оборудования нет."""


class EquipmentDataError(DataError):
    """Данные типа оборудования не прошли проверку."""


class EquipmentInUseError(InUseError):
    """Тип оборудования нельзя удалить: его требуют заявки."""


def to_equipment_read(equipment: Equipment, request_count: int) -> EquipmentRead:
    return EquipmentRead(
        id=equipment.id,
        name=equipment.name,
        description=equipment.description,
        request_count=request_count,
    )


async def list_equipment(session: AsyncSession) -> list[EquipmentRead]:
    return [
        to_equipment_read(equipment, count)
        for equipment, count in await equipment_repository.list_equipment(session)
    ]


async def create_equipment(session: AsyncSession, payload: EquipmentWrite) -> EquipmentRead:
    await check_name_is_free(session, payload.name)
    equipment = equipment_repository.add_equipment(session, payload.model_dump())
    await session.flush()
    await session.commit()
    return to_equipment_read(equipment, 0)


async def update_equipment(
    session: AsyncSession, equipment_id: int, payload: EquipmentWrite
) -> EquipmentRead:
    equipment = await find_equipment(session, equipment_id)
    await check_name_is_free(session, payload.name, except_id=equipment_id)
    equipment_repository.apply_changes(equipment, payload.model_dump())
    await session.commit()
    return to_equipment_read(
        equipment, await equipment_repository.count_requests(session, equipment_id)
    )


async def delete_equipment(session: AsyncSession, equipment_id: int) -> None:
    """Удаляет тип оборудования, если его не требует ни одна заявка."""
    equipment = await find_equipment(session, equipment_id)
    used = await equipment_repository.count_requests(session, equipment_id)
    if used:
        raise EquipmentInUseError(
            f"«{equipment.name}» нельзя удалить: его требуют заявки ({used}). "
            "Сначала снимите требование в заявках"
        )
    await equipment_repository.delete_equipment(session, equipment)
    await session.commit()


async def find_equipment(session: AsyncSession, equipment_id: int) -> Equipment:
    equipment = await equipment_repository.get_equipment(session, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError(f"Оборудование №{equipment_id} не найдено")
    return equipment


async def check_name_is_free(
    session: AsyncSession, name: str, except_id: int | None = None
) -> None:
    same_name = await equipment_repository.find_equipment_by_name(session, name)
    if same_name is not None and same_name.id != except_id:
        raise EquipmentDataError([f"«{name}» уже есть в справочнике оборудования"])
