"""Офисы: справочник точек, из которых исполнители выезжают на смену."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.models import Office
from src.repositories.offices import offices_repository
from src.schemas.offices import OfficeRead, OfficeWrite


class OfficeNotFoundError(NotFoundError):
    """Офиса с таким номером нет."""


class OfficeDataError(DataError):
    """Данные офиса не прошли проверку."""


class OfficeInUseError(InUseError):
    """Офис нельзя удалить: у него есть заявки, бригады, планы или диспетчеры."""


def to_office_read(office: Office, engineer_count: int) -> OfficeRead:
    return OfficeRead(
        id=office.id,
        name=office.name,
        address=office.address,
        latitude=float(office.latitude),
        longitude=float(office.longitude),
        engineer_count=engineer_count,
    )


async def list_offices(session: AsyncSession) -> list[OfficeRead]:
    return [
        to_office_read(office, count)
        for office, count in await offices_repository.list_offices(session)
    ]


async def create_office(session: AsyncSession, payload: OfficeWrite) -> OfficeRead:
    await check_name_is_free(session, payload.name)
    office = offices_repository.add_office(session, payload.model_dump())
    await session.flush()
    await session.commit()
    return to_office_read(office, 0)


async def update_office(session: AsyncSession, office_id: int, payload: OfficeWrite) -> OfficeRead:
    """Меняет офис; если сдвинулись координаты — сдвигает старт бригад, выезжающих из него."""
    office = await find_office(session, office_id)
    await check_name_is_free(session, payload.name, except_id=office_id)
    offices_repository.apply_changes(office, payload.model_dump())
    await session.flush()
    await offices_repository.move_engineers_to_office(session, office)
    await session.commit()
    return to_office_read(office, await offices_repository.count_engineers(session, office_id))


async def delete_office(session: AsyncSession, office_id: int) -> None:
    """Удаляет пустой офис. Офис с данными не удалить: заявки и бригады остались бы ничьими."""
    office = await find_office(session, office_id)
    usages = {label: count for label, count in (await offices_repository.count_usages(session, office_id)).items() if count}
    if usages:
        listed = ", ".join(f"{label} {count}" for label, count in usages.items())
        raise OfficeInUseError(f"Офис «{office.name}» нельзя удалить: у него есть {listed}")
    await offices_repository.delete_office(session, office)
    await session.commit()


async def find_office(session: AsyncSession, office_id: int) -> Office:
    office = await offices_repository.get_office(session, office_id)
    if office is None:
        raise OfficeNotFoundError(f"Офис №{office_id} не найден")
    return office


async def check_name_is_free(
    session: AsyncSession, name: str, except_id: int | None = None
) -> None:
    same_name = await offices_repository.find_office_by_name(session, name)
    if same_name is not None and same_name.id != except_id:
        raise OfficeDataError([f"офис «{name}» уже есть в справочнике"])
