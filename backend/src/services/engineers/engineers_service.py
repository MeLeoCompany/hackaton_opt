"""Исполнители: просмотр, создание, изменение, удаление."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.free_id import smallest_free_id
from src.core.local_day import day_bounds, local_timezone
from src.models import Engineer, Skill
from src.repositories.engineers import engineers_repository
from src.repositories.references import references_repository
from src.schemas.engineers import EngineerCreate, EngineerImportReport, EngineerRead, EngineerWrite
from src.services.engineers.engineers_csv import (
    EngineerReferenceLookup,
    build_engineers_csv,
    format_datetime,
    parse_engineers_csv,
)
from src.services.requests.requests_csv import reference_options


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


async def export_engineers_csv(session: AsyncSession, plan_date: date | None = None) -> str:
    """Исполнители дня в CSV — слепок смен, который можно загрузить обратно или в другой день."""
    engineers = await list_engineers(session, plan_date)
    names = await reference_names(session)
    timezone = local_timezone()
    return build_engineers_csv(
        [
            {
                "id": engineer.id,
                "имя": engineer.name,
                "широта_старта": f"{engineer.start_latitude:.6f}",
                "долгота_старта": f"{engineer.start_longitude:.6f}",
                "транспорт": names["transports"].get(engineer.transport_id, ""),
                "навыки": ", ".join(
                    names["skills"].get(skill_id, str(skill_id)) for skill_id in engineer.skill_ids
                ),
                "смена_начало": format_datetime(engineer.shift_start, timezone),
                "смена_конец": format_datetime(engineer.shift_end, timezone),
            }
            for engineer in engineers
        ]
    )


async def reference_names(session: AsyncSession) -> dict[str, dict[int, str]]:
    """Названия транспорта и навыков по номеру — для выгрузки в CSV."""
    transports = await references_repository.list_transports(session)
    skills = await references_repository.list_skills(session)
    return {
        "transports": {transport.id: transport.name for transport in transports},
        "skills": {skill.id: skill.name for skill in skills},
    }


def copy_rows_to_day(rows: list[dict], plan_date: date) -> None:
    """Переносит смены в выбранный день: время суток то же, номера новые.

    Так слепок одного дня превращается в самостоятельную копию на другой день,
    а не перезаписывает исходных исполнителей.
    """
    timezone = local_timezone()
    for fields in rows:
        start, end = fields["shift_start"], fields["shift_end"]
        day_offset = (end.astimezone(timezone).date() - start.astimezone(timezone).date()).days
        local_start = start.astimezone(timezone)
        local_end = end.astimezone(timezone)
        fields["shift_start"] = local_start.replace(
            year=plan_date.year, month=plan_date.month, day=plan_date.day
        )
        fields["shift_end"] = local_end.replace(
            year=plan_date.year, month=plan_date.month, day=plan_date.day
        ) + timedelta(days=day_offset)
        fields["id"] = None


async def import_engineers_csv(
    session: AsyncSession, content: bytes, plan_date: date | None = None
) -> EngineerImportReport:
    """Загружает исполнителей из CSV одной транзакцией.

    Если хоть одна строка с ошибкой — не сохраняется ничего. Исполнитель с существующим
    номером обновляется, без номера — добавляется. Если указан plan_date, файл переносится
    в этот день копией: время смен то же, даты новые, номера новые.
    """
    await engineers_repository.lock_engineer_ids(session)
    transports = await references_repository.list_transports(session)
    skills = await references_repository.list_skills(session)
    references = EngineerReferenceLookup(
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
    )

    parsed = parse_engineers_csv(content, references, local_timezone())
    if parsed.errors:
        raise EngineerDataError(parsed.errors)
    if not parsed.rows:
        raise EngineerDataError(["в файле нет ни одного исполнителя"])

    if plan_date is not None:
        copy_rows_to_day(parsed.rows, plan_date)

    skill_by_id = {skill.id: skill for skill in skills}
    taken_ids = await engineers_repository.list_engineer_ids(session)
    taken_ids.update(row["id"] for row in parsed.rows if row["id"] is not None)

    created = 0
    updated = 0
    for fields in parsed.rows:
        row_skills = [skill_by_id[skill_id] for skill_id in fields["skill_ids"]]
        values = {name: value for name, value in fields.items() if name not in {"id", "skill_ids"}}

        existing = (
            await engineers_repository.get_engineer(session, fields["id"])
            if fields["id"] is not None
            else None
        )
        if existing is not None:
            engineers_repository.apply_changes(existing, values, row_skills)
            updated += 1
            continue

        identifier = fields["id"] if fields["id"] is not None else smallest_free_id(taken_ids)
        taken_ids.add(identifier)
        engineers_repository.add_engineer(session, {"id": identifier, **values}, row_skills)
        created += 1

    await session.flush()
    await session.commit()
    return EngineerImportReport(created=created, updated=updated)
