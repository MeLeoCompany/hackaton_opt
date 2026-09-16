"""Исполнители: просмотр, создание, изменение, удаление."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.free_id import smallest_free_id
from src.core.local_day import day_bounds
from src.models import Engineer, Skill
from src.repositories.engineers import engineers_repository
from src.repositories.references import references_repository
from src.schemas.engineers import EngineerCreate, EngineerRead, EngineerWrite


class EngineerNotFoundError(NotFoundError):
    """Исполнителя с таким номером нет."""


class EngineerInUseError(InUseError):
    """Исполнителя нельзя удалить: на него ссылаются планы или события перепланирования."""


class EngineerDataError(DataError):
    """Данные исполнителя не прошли проверку."""


def to_engineer_read(engineer: Engineer) -> EngineerRead:
    """Исполнитель из БД -> ответ API: навыки отдаются списком номеров."""
    return EngineerRead(
        id=engineer.id,
        name=engineer.name,
        start_latitude=float(engineer.start_latitude),
        start_longitude=float(engineer.start_longitude),
        shift_start=engineer.shift_start,
        shift_end=engineer.shift_end,
        transport_id=engineer.transport_id,
        skill_ids=sorted(skill.id for skill in engineer.skills),
    )


async def list_engineers(
    session: AsyncSession, plan_date: date | None = None
) -> list[EngineerRead]:
    """Все исполнители или только те, чья смена попадает в выбранный день."""
    if plan_date is None:
        engineers = await engineers_repository.list_engineers(session)
    else:
        day_start, day_end = day_bounds(plan_date)
        engineers = await engineers_repository.list_engineers_in_period(session, day_start, day_end)
    return [to_engineer_read(engineer) for engineer in engineers]


async def get_engineer(session: AsyncSession, engineer_id: int) -> EngineerRead:
    return to_engineer_read(await find_engineer(session, engineer_id))


async def create_engineer(session: AsyncSession, payload: EngineerCreate) -> EngineerRead:
    await engineers_repository.lock_engineer_ids(session)
    skills = await check_references(session, payload)

    if (
        payload.id is not None
        and await engineers_repository.get_engineer(session, payload.id) is not None
    ):
        raise EngineerDataError(
            [f"исполнитель №{payload.id} уже существует — измените его или укажите другой номер"]
        )

    fields = payload.model_dump(exclude={"skill_ids"})
    if fields["id"] is None:
        fields["id"] = smallest_free_id(await engineers_repository.list_engineer_ids(session))

    engineer = engineers_repository.add_engineer(session, fields, skills)
    await session.flush()
    await session.commit()
    return to_engineer_read(engineer)


async def update_engineer(
    session: AsyncSession, engineer_id: int, payload: EngineerWrite
) -> EngineerRead:
    engineer = await find_engineer(session, engineer_id)
    skills = await check_references(session, payload)
    engineers_repository.apply_changes(engineer, payload.model_dump(exclude={"skill_ids"}), skills)
    await session.commit()
    return to_engineer_read(engineer)


async def delete_engineer(session: AsyncSession, engineer_id: int) -> None:
    engineer = await find_engineer(session, engineer_id)

    assignments, events = await engineers_repository.count_engineer_usages(session, engineer_id)
    if assignments or events:
        raise EngineerInUseError(
            f"Исполнителя №{engineer_id} нельзя удалить: он есть в планах ({assignments}) "
            f"и событиях перепланирования ({events})"
        )

    await engineers_repository.delete_engineer(session, engineer)
    await session.commit()


async def find_engineer(session: AsyncSession, engineer_id: int) -> Engineer:
    engineer = await engineers_repository.get_engineer(session, engineer_id)
    if engineer is None:
        raise EngineerNotFoundError(f"Исполнитель №{engineer_id} не найден")
    return engineer


async def check_references(session: AsyncSession, payload: EngineerWrite) -> list[Skill]:
    """Проверяет, что транспорт и навыки есть в справочниках; возвращает найденные навыки."""
    problems = []

    transports = await references_repository.list_transports(session)
    if payload.transport_id not in {transport.id for transport in transports}:
        problems.append(f"транспорта №{payload.transport_id} нет в справочнике")

    skills = await engineers_repository.get_skills_by_ids(session, payload.skill_ids)
    missing_skill_ids = sorted(set(payload.skill_ids) - {skill.id for skill in skills})
    if missing_skill_ids:
        listed = ", ".join(f"№{skill_id}" for skill_id in missing_skill_ids)
        problems.append(f"навыков {listed} нет в справочнике")

    if problems:
        raise EngineerDataError(problems)
    return skills
