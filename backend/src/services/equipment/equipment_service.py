"""Оборудование: справочник того, что техник привозит на заявку."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.models import Equipment, Transport
from src.repositories.equipment import equipment_repository
from src.schemas.equipment import CapacityRow, EquipmentRead, EquipmentWrite


class EquipmentNotFoundError(NotFoundError):
    """Такого типа оборудования нет."""


class EquipmentDataError(DataError):
    """Данные типа оборудования не прошли проверку."""


class EquipmentInUseError(InUseError):
    """Тип оборудования нельзя удалить: его требуют заявки."""


def to_equipment_read(
    equipment: Equipment, request_count: int, engineer_count: int = 0
) -> EquipmentRead:
    return EquipmentRead(
        id=equipment.id,
        name=equipment.name,
        description=equipment.description,
        request_count=request_count,
        engineer_count=engineer_count,
    )


async def list_equipment(session: AsyncSession) -> list[EquipmentRead]:
    return [
        to_equipment_read(equipment, requests, engineers)
        for equipment, requests, engineers in await equipment_repository.list_equipment(session)
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
        equipment,
        await equipment_repository.count_requests(session, equipment_id),
        await equipment_repository.count_engineers(session, equipment_id),
    )


async def delete_equipment(session: AsyncSession, equipment_id: int) -> None:
    """Удаляет тип оборудования, если его не требуют заявки и нет ни у одной бригады."""
    equipment = await find_equipment(session, equipment_id)
    requests = await equipment_repository.count_requests(session, equipment_id)
    engineers = await equipment_repository.count_engineers(session, equipment_id)
    if requests or engineers:
        where = []
        if requests:
            where.append(f"требуется в заявках ({requests})")
        if engineers:
            where.append(f"есть у бригад ({engineers})")
        raise EquipmentInUseError(
            f"«{equipment.name}» нельзя удалить: {' и '.join(where)}. "
            "Сначала уберите его из заявок и бригад"
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


async def list_capacity(session: AsyncSession) -> list[CapacityRow]:
    """Справочник ёмкости строками: все пары «транспорт × оборудование».

    Показываем и пары, которых в базе ещё нет: иначе новый тип оборудования не завести
    в справочнике — его просто не было бы видно.
    """
    transports = (await session.execute(select(Transport).order_by(Transport.id))).scalars().all()
    equipment = (await session.execute(select(Equipment).order_by(Equipment.id))).scalars().all()
    known = await equipment_repository.capacity_map(session)
    return [
        CapacityRow(
            transport_id=transport.id,
            transport_name=transport.name,
            equipment_id=item.id,
            equipment_name=item.name,
            max_quantity=known.get((transport.id, item.id), 0),
        )
        for transport in transports
        for item in equipment
    ]


async def save_capacity(session: AsyncSession, rows: list[CapacityRow]) -> list[CapacityRow]:
    """Сохранить изменившиеся пределы. Что не прислали — остаётся как было."""
    for row in rows:
        await equipment_repository.set_capacity(
            session, row.transport_id, row.equipment_id, row.max_quantity
        )
    await session.commit()
    return await list_capacity(session)
