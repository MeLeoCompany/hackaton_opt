"""Исполнители: просмотр, создание, изменение, удаление."""

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.free_id import smallest_free_id
from src.core.local_day import day_bounds, local_timezone
from src.models import Engineer, Office, Skill
from src.repositories.brigades import brigades_repository
from src.repositories.engineers import engineers_repository
from src.repositories.offices import offices_repository
from src.repositories.references import references_repository
from src.schemas.bulk import BulkDeleteProblem, BulkDeleteReport, BulkUpdateReport
from src.schemas.engineers import (
    EngineerBulkUpdate,
    EngineerCreate,
    EngineerEquipmentItem,
    EngineerImportReport,
    EngineerRead,
    EngineerWrite,
)
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
        brigade_id=engineer.brigade_id,
        start_latitude=float(engineer.start_latitude),
        start_longitude=float(engineer.start_longitude),
        shift_start=engineer.shift_start,
        shift_end=engineer.shift_end,
        transport_id=engineer.transport_id,
        office_id=engineer.office_id,
        start_at_office=engineer.start_at_office,
        skill_ids=sorted(skill.id for skill in engineer.skills),
        equipment=[
            EngineerEquipmentItem(equipment_id=item.equipment_id, quantity=item.quantity)
            for item in engineer.equipment_items
        ],
    )


async def list_engineers(
    session: AsyncSession, office_id: int, plan_date: date | None = None
) -> list[EngineerRead]:
    """Все бригады офиса или только те, чья смена попадает в выбранный день."""
    if plan_date is None:
        engineers = await engineers_repository.list_engineers(session, office_id=office_id)
    else:
        day_start, day_end = day_bounds(plan_date)
        engineers = await engineers_repository.list_engineers_in_period(
            session, day_start, day_end, office_id=office_id
        )
    return [to_engineer_read(engineer) for engineer in engineers]


async def get_engineer(session: AsyncSession, engineer_id: int, office_id: int) -> EngineerRead:
    return to_engineer_read(await find_engineer(session, engineer_id, office_id))


async def create_engineer(
    session: AsyncSession, payload: EngineerCreate, office_id: int
) -> EngineerRead:
    await engineers_repository.lock_engineer_ids(session)
    skills = await check_references(session, payload)
    await check_brigade_is_free(session, payload)

    taken = (
        await engineers_repository.get_engineer(session, payload.id)
        if payload.id is not None
        else None
    )
    if taken is not None:
        raise EngineerDataError(
            [
                f"номер №{payload.id} уже занят исполнителем «{taken.name}»"
                f"{await elsewhere(session, taken.office_id, office_id)}. Номера общие для всех "
                "офисов — оставьте поле пустым, и номер подберётся сам"
            ]
        )

    fields = await with_office_start(
        session,
        {
            **payload.model_dump(exclude={"skill_ids", "equipment"}),
            "office_id": office_id,
            "name": await brigade_name(session, payload.brigade_id, office_id),
        },
    )
    if fields["id"] is None:
        fields["id"] = smallest_free_id(await engineers_repository.list_engineer_ids(session))

    engineer = engineers_repository.add_engineer(session, fields, skills)
    engineers_repository.set_equipment(engineer, equipment_quantities(payload))
    await session.flush()
    await session.commit()
    return to_engineer_read(engineer)


async def update_engineer(
    session: AsyncSession, engineer_id: int, payload: EngineerWrite, office_id: int
) -> EngineerRead:
    engineer = await find_engineer(session, engineer_id, office_id)
    skills = await check_references(session, payload)
    await check_brigade_is_free(session, payload, engineer_id=engineer_id)
    # у уже заведённой смены бригада может быть выключена — смену всё равно можно поправить
    fields = await with_office_start(
        session,
        {
            **payload.model_dump(exclude={"skill_ids", "equipment"}),
            "office_id": office_id,
            "name": await brigade_name(
                session,
                payload.brigade_id,
                office_id,
                allow_inactive=payload.brigade_id == engineer.brigade_id,
            ),
        },
    )
    engineers_repository.apply_changes(engineer, fields, skills)
    engineers_repository.set_equipment(engineer, equipment_quantities(payload))
    await session.commit()
    return to_engineer_read(engineer)


async def delete_engineer(session: AsyncSession, engineer_id: int, office_id: int) -> None:
    engineer = await find_engineer(session, engineer_id, office_id)

    assignments, events = await engineers_repository.count_engineer_usages(session, engineer_id)
    if assignments or events:
        raise EngineerInUseError(
            f"Исполнителя №{engineer_id} нельзя удалить: он есть в планах ({assignments}) "
            f"и событиях перепланирования ({events})"
        )

    await engineers_repository.delete_engineer(session, engineer)
    await session.commit()


async def delete_engineers(
    session: AsyncSession, engineer_ids: list[int], office_id: int
) -> BulkDeleteReport:
    """Удаляет выбранные смены: те, что можно, — остальные возвращает с причинами.

    Смена, попавшая в план, остаётся: по ней ездила бригада. Прочие выбранные удаляются —
    одна занятая смена не должна отменять удаление всех остальных.
    """
    problems = []
    deleted = 0
    for engineer_id in dict.fromkeys(engineer_ids):
        try:
            await delete_engineer(session, engineer_id, office_id)
            deleted += 1
        except (EngineerNotFoundError, EngineerInUseError) as error:
            problems.append(BulkDeleteProblem(id=engineer_id, reason=str(error)))
    return BulkDeleteReport(deleted=deleted, problems=problems)


async def update_engineers(
    session: AsyncSession, payload: EngineerBulkUpdate, office_id: int
) -> BulkUpdateReport:
    """Групповая правка смен: меняет только отмеченные оператором поля.

    Либо меняются все смены, либо ни одна: сначала проверяем справочники, длину смены и то,
    что бригада не окажется в двух сменах сразу.
    """
    unique_ids = list(dict.fromkeys(payload.engineer_ids))
    engineers = [await find_engineer(session, engineer_id, office_id) for engineer_id in unique_ids]
    changes = payload.changes()

    skills = None
    if changes.get("skill_ids") is not None:
        skills = await check_bulk_references(session, changes)
    elif changes.get("transport_id") is not None:
        await check_bulk_references(session, changes)

    shifts = {
        engineer.id: new_shift(engineer, changes, payload.move_to_day) for engineer in engineers
    }
    problems = [
        f"смена №{engineer.id}: конец смены должен быть позже начала "
        f"({format_local_shift(shifts[engineer.id])})"
        for engineer in engineers
        if shifts[engineer.id]["shift_end"] <= shifts[engineer.id]["shift_start"]
    ]
    problems += await busy_brigades(session, engineers, shifts)
    if problems:
        raise EngineerDataError(problems)

    fields = {name: value for name, value in changes.items() if name != "skill_ids"}
    for engineer in engineers:
        engineer_fields = await with_office_start(
            session, {**fields, **shifts[engineer.id], "office_id": office_id}
        )
        engineer_fields.pop("office_id")
        engineers_repository.apply_changes(
            engineer, engineer_fields, skills if skills is not None else list(engineer.skills)
        )
    await session.commit()
    return BulkUpdateReport(updated=len(engineers))


def new_shift(engineer: Engineer, changes: dict, move_to_day: date | None) -> dict:
    """Смена после правки: что задали явно, что перенесли на другой день, что было."""
    timezone = local_timezone()
    shift = {
        "shift_start": changes.get("shift_start") or engineer.shift_start,
        "shift_end": changes.get("shift_end") or engineer.shift_end,
    }
    if move_to_day is not None:
        # день другой, время то же: ночная смена так и остаётся ночной
        moved = {
            name: moment.astimezone(timezone).replace(
                year=move_to_day.year, month=move_to_day.month, day=move_to_day.day
            )
            for name, moment in shift.items()
        }
        if moved["shift_end"] <= moved["shift_start"]:
            moved["shift_end"] += timedelta(days=1)
        shift = moved
    return shift


async def busy_brigades(
    session: AsyncSession, engineers: list[Engineer], shifts: dict[int, dict]
) -> list[str]:
    """Одна бригада — одна смена за раз: и среди чужих смен, и среди правленных вместе."""
    changed = {engineer.id for engineer in engineers}
    problems = []
    for engineer in engineers:
        shift = shifts[engineer.id]
        others = [
            other
            for other in await engineers_repository.list_brigade_shifts(
                session, engineer.brigade_id, shift["shift_start"], shift["shift_end"]
            )
            if other.id not in changed
        ]
        together = [
            other
            for other in engineers
            if other.id != engineer.id
            and other.brigade_id == engineer.brigade_id
            and shifts[other.id]["shift_start"] < shift["shift_end"]
            and shifts[other.id]["shift_end"] > shift["shift_start"]
        ]
        if others or together:
            problems.append(
                f"у бригады «{engineer.name}» после правки две смены сразу "
                f"({format_local_shift(shift)}) — так нельзя"
            )
    return problems


def format_local_shift(shift: dict) -> str:
    timezone = local_timezone()
    start = shift["shift_start"].astimezone(timezone)
    end = shift["shift_end"].astimezone(timezone)
    return f"{start:%d.%m %H:%M}–{end:%d.%m %H:%M}"


async def check_bulk_references(session: AsyncSession, changes: dict) -> list[Skill] | None:
    """Проверяет только заданные поля: транспорт и навыки. Возвращает навыки, если их меняют."""
    problems = []
    if changes.get("transport_id") is not None:
        transports = await references_repository.list_transports(session)
        if changes["transport_id"] not in {transport.id for transport in transports}:
            problems.append(f"транспорта №{changes['transport_id']} нет в справочнике")

    skills = None
    if changes.get("skill_ids") is not None:
        skills = await engineers_repository.get_skills_by_ids(session, changes["skill_ids"])
        missing = sorted(set(changes["skill_ids"]) - {skill.id for skill in skills})
        if missing:
            listed = ", ".join(f"№{skill_id}" for skill_id in missing)
            problems.append(f"навыков {listed} нет в справочнике")
    if problems:
        raise EngineerDataError(problems)
    return skills


async def brigade_name(
    session: AsyncSession, brigade_id: int, office_id: int, *, allow_inactive: bool = False
) -> str:
    """Название бригады смены — из справочника бригад офиса; выключенной новые смены не заводят."""
    brigade = await brigades_repository.get_brigade(session, brigade_id)
    if brigade is None or brigade.office_id != office_id:
        raise EngineerDataError([f"бригады №{brigade_id} нет в справочнике бригад офиса"])
    if not brigade.is_active and not allow_inactive:
        raise EngineerDataError([f"бригада «{brigade.name}» выключена — включите её в справочнике"])
    return brigade.name


async def check_brigade_is_free(
    session: AsyncSession, payload: EngineerWrite, *, engineer_id: int | None = None
) -> None:
    """Одна бригада — одна смена за раз: пересечение с её же сменой не даём завести."""
    busy = [
        shift
        for shift in await engineers_repository.list_brigade_shifts(
            session, payload.brigade_id, payload.shift_start, payload.shift_end
        )
        if shift.id != engineer_id
    ]
    if busy:
        shift = busy[0]
        raise EngineerDataError(
            [
                f"у бригады «{shift.name}» уже есть смена {format_local_period(shift)} "
                "— одна бригада не может работать в двух сменах сразу"
            ]
        )


def format_local_period(engineer: Engineer) -> str:
    """Смена по-московски: «17.08.2026 09:00–18:00»."""
    start = engineer.shift_start.astimezone(local_timezone())
    end = engineer.shift_end.astimezone(local_timezone())
    tail = end.strftime("%H:%M") if end.date() == start.date() else end.strftime("%d.%m.%Y %H:%M")
    return f"{start.strftime('%d.%m.%Y %H:%M')}–{tail}"


async def find_engineer(session: AsyncSession, engineer_id: int, office_id: int) -> Engineer:
    """Бригада офиса. Чужая выглядит как несуществующая."""
    engineer = await engineers_repository.get_engineer(session, engineer_id)
    if engineer is None or engineer.office_id != office_id:
        raise EngineerNotFoundError(f"Исполнитель №{engineer_id} не найден")
    return engineer


async def with_office_start(session: AsyncSession, fields: dict) -> dict:
    """Выезжает из своего офиса — старт ставится в координаты офиса, что бы ни прислал клиент.

    Так старт бригады и точка офиса не расходятся: планировщик читает координаты
    исполнителя, а правду о них знает справочник офисов.
    """
    if not fields.get("start_at_office"):
        return fields
    office = await offices_repository.get_office(session, fields["office_id"])
    if office is None:
        raise EngineerDataError([f"офиса №{fields['office_id']} нет в справочнике"])
    return {**fields, "start_latitude": office.latitude, "start_longitude": office.longitude}


def equipment_quantities(payload: EngineerWrite) -> dict[int, int]:
    return {item.equipment_id: item.quantity for item in payload.equipment}


async def check_references(session: AsyncSession, payload: EngineerWrite) -> list[Skill]:
    """Проверяет транспорт, навыки и оборудование по справочникам; возвращает навыки."""
    problems = []

    transports = await references_repository.list_transports(session)
    if payload.transport_id not in {transport.id for transport in transports}:
        problems.append(f"транспорта №{payload.transport_id} нет в справочнике")

    skills = await engineers_repository.get_skills_by_ids(session, payload.skill_ids)
    missing_skill_ids = sorted(set(payload.skill_ids) - {skill.id for skill in skills})
    if missing_skill_ids:
        listed = ", ".join(f"№{skill_id}" for skill_id in missing_skill_ids)
        problems.append(f"навыков {listed} нет в справочнике")

    known_equipment = {item.id for item in await references_repository.list_equipment(session)}
    missing_equipment = [
        item.equipment_id for item in payload.equipment if item.equipment_id not in known_equipment
    ]
    if missing_equipment:
        listed = ", ".join(f"№{equipment_id}" for equipment_id in missing_equipment)
        problems.append(f"оборудования {listed} нет в справочнике")

    if problems:
        raise EngineerDataError(problems)
    return skills


async def export_engineers_csv(
    session: AsyncSession, office_id: int, plan_date: date | None = None
) -> str:
    """Бригады офиса за день в CSV — слепок смен, который можно загрузить обратно или в другой день."""
    engineers = await list_engineers(session, office_id, plan_date)
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
                "старт_из_офиса": "да" if engineer.start_at_office else "нет",
                "навыки": ", ".join(
                    names["skills"].get(skill_id, str(skill_id)) for skill_id in engineer.skill_ids
                ),
                "смена_начало": format_datetime(engineer.shift_start, timezone),
                "смена_конец": format_datetime(engineer.shift_end, timezone),
                "оборудование": ", ".join(
                    f"{names['equipment'].get(item.equipment_id, item.equipment_id)}: {item.quantity}"
                    for item in engineer.equipment
                ),
            }
            for engineer in engineers
        ]
    )


async def reference_names(session: AsyncSession) -> dict[str, dict[int, str]]:
    """Названия транспорта, навыков и оборудования по номеру — для выгрузки в CSV."""
    transports = await references_repository.list_transports(session)
    skills = await references_repository.list_skills(session)
    equipment = await references_repository.list_equipment(session)
    return {
        "transports": {transport.id: transport.name for transport in transports},
        "skills": {skill.id: skill.name for skill in skills},
        "equipment": {item.id: item.name for item in equipment},
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


async def brigade_shift_problems(
    session: AsyncSession,
    values: dict,
    file_shifts: dict[int, list[tuple[datetime, datetime]]],
    *,
    engineer_id: int | None,
) -> list[str]:
    """Смена бригады из строки CSV не должна пересекаться ни с файлом, ни с базой."""
    brigade_id, start, end = values["brigade_id"], values["shift_start"], values["shift_end"]
    period = f"{values['name']} {start.astimezone(local_timezone()).strftime('%d.%m.%Y %H:%M')}"
    problems = []
    if any(
        start < other_end and end > other_start
        for other_start, other_end in file_shifts.get(brigade_id, [])
    ):
        problems.append(f"{period}: в файле у бригады две смены сразу — оставьте одну")
    else:
        busy = [
            shift
            for shift in await engineers_repository.list_brigade_shifts(
                session, brigade_id, start, end
            )
            if shift.id != engineer_id
        ]
        if busy:
            problems.append(
                f"{period}: у бригады уже есть смена {format_local_period(busy[0])} "
                "— одна бригада не может работать в двух сменах сразу"
            )
    file_shifts.setdefault(brigade_id, []).append((start, end))
    return problems


async def import_engineers_csv(
    session: AsyncSession, content: bytes, office_id: int, plan_date: date | None = None
) -> EngineerImportReport:
    """Загружает исполнителей из CSV одной транзакцией.

    Если хоть одна строка с ошибкой — не сохраняется ничего. Исполнитель с существующим
    номером обновляется, без номера — добавляется. Если указан plan_date, файл переносится
    в этот день копией: время смен то же, даты новые, номера новые.
    """
    await engineers_repository.lock_engineer_ids(session)
    transports = await references_repository.list_transports(session)
    skills = await references_repository.list_skills(session)
    equipment = await references_repository.list_equipment(session)
    references = EngineerReferenceLookup(
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
        equipment=reference_options([(item.id, item.name) for item in equipment]),
    )
    office = await offices_repository.get_office(session, office_id)

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

    # колонка «имя» — бригада офиса; бригады, которой ещё нет в справочнике, заводим сами
    # (без входа в приложение — логин и пароль ей зададут в справочнике бригад)
    brigades: dict[str, int] = {}

    async def brigade_id_of(name: str) -> int:
        if name not in brigades:
            brigade = await brigades_repository.find_by_name(session, office_id, name)
            if brigade is None:
                brigade = brigades_repository.add_brigade(
                    session, {"office_id": office_id, "name": name, "is_active": True}
                )
                await session.flush()
            brigades[name] = brigade.id
        return brigades[name]

    created = 0
    updated = 0
    # одна бригада — одна смена за раз: проверяем и по файлу, и по уже заведённым сменам
    shift_errors: list[str] = []
    file_shifts: dict[int, list[tuple[datetime, datetime]]] = {}
    for fields in parsed.rows:
        row_skills = [skill_by_id[skill_id] for skill_id in fields["skill_ids"]]
        values = {
            name: value
            for name, value in fields.items()
            if name not in {"id", "skill_ids", "equipment"}
        }
        # колонки «оборудование» нет в файле — запас бригады не трогаем
        quantities = fields.get("equipment")
        values["office_id"] = office_id
        values["brigade_id"] = await brigade_id_of(values["name"])
        # из офиса — старт в точке офиса, как и при правке в интерфейсе
        if values["start_at_office"]:
            values["start_latitude"] = office.latitude
            values["start_longitude"] = office.longitude

        existing = (
            await engineers_repository.get_engineer(session, fields["id"])
            if fields["id"] is not None
            else None
        )
        shift_errors += await brigade_shift_problems(
            session, values, file_shifts, engineer_id=existing.id if existing is not None else None
        )
        if existing is not None and existing.office_id != office_id:
            raise EngineerDataError(
                [
                    f"исполнитель №{fields['id']} есть в другом офисе — уберите номер или укажите другой"
                ]
            )
        if existing is not None:
            engineers_repository.apply_changes(existing, values, row_skills)
            if quantities is not None:
                engineers_repository.set_equipment(existing, quantities)
            updated += 1
            continue

        identifier = fields["id"] if fields["id"] is not None else smallest_free_id(taken_ids)
        taken_ids.add(identifier)
        engineer = engineers_repository.add_engineer(
            session, {"id": identifier, **values}, row_skills
        )
        engineers_repository.set_equipment(engineer, quantities or {})
        created += 1

    await session.flush()
    if shift_errors:
        raise EngineerDataError(shift_errors)
    await session.commit()
    return EngineerImportReport(created=created, updated=updated)


async def elsewhere(session: AsyncSession, taken_office_id: int | None, office_id: int) -> str:
    """Где занят номер: в другом офисе запись не видна, и без пояснения ошибка непонятна."""
    if taken_office_id == office_id:
        return " этого офиса"
    office = await session.get(Office, taken_office_id) if taken_office_id else None
    return f" офиса «{office.name}»" if office else " другого офиса"
