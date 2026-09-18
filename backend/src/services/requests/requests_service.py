"""Заявки: просмотр, создание, изменение, удаление и загрузка из CSV."""

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.free_id import smallest_free_id
from src.core.local_day import day_bounds, local_timezone
from src.models import Request
from src.repositories.references import references_repository
from src.repositories.requests import requests_repository
from src.schemas.requests import (
    RequestActivityReport,
    RequestCreate,
    RequestImportReport,
    RequestWrite,
)
from src.services.requests.requests_csv import (
    ReferenceLookup,
    WorkTypeNorm,
    build_requests_csv,
    format_datetime,
    parse_requests_csv,
    reference_options,
)


class RequestNotFoundError(NotFoundError):
    """Заявки с таким номером нет."""


class RequestInUseError(InUseError):
    """Заявку нельзя удалить: на неё ссылаются планы или события перепланирования."""


class RequestDataError(DataError):
    """Данные заявки не прошли проверку."""


async def list_requests(
    session: AsyncSession, office_id: int, plan_date: date | None = None
) -> list[Request]:
    """Все заявки офиса или только те, чьё окно попадает в выбранный день."""
    if plan_date is None:
        return await requests_repository.list_requests(session, office_id=office_id)
    day_start, day_end = day_bounds(plan_date)
    return await requests_repository.list_requests_in_period(
        session, day_start, day_end, office_id=office_id
    )


async def get_request(session: AsyncSession, request_id: int, office_id: int) -> Request:
    """Заявка офиса. Чужая выглядит как несуществующая: о заявках других офисов не сообщаем."""
    request = await requests_repository.get_request(session, request_id)
    if request is None or request.office_id != office_id:
        raise RequestNotFoundError(f"Заявка №{request_id} не найдена")
    return request


async def create_request(session: AsyncSession, payload: RequestCreate, office_id: int) -> Request:
    await requests_repository.lock_request_ids(session)
    await check_references_exist(session, payload)
    await apply_work_type_norms(session, payload)

    if (
        payload.id is not None
        and await requests_repository.get_request(session, payload.id) is not None
    ):
        raise RequestDataError(
            [f"заявка №{payload.id} уже существует — измените её или укажите другой номер"]
        )

    fields = {**payload.model_dump(exclude={"equipment"}), "office_id": office_id}
    if fields["id"] is None:
        fields["id"] = smallest_free_id(await requests_repository.list_request_ids(session))

    request = requests_repository.add_request(session, fields, equipment_quantities(payload))
    await session.flush()
    await session.commit()
    return request


async def update_request(
    session: AsyncSession, request_id: int, payload: RequestWrite, office_id: int
) -> Request:
    request = await get_request(session, request_id, office_id)
    await check_references_exist(session, payload)
    await apply_work_type_norms(session, payload)
    requests_repository.apply_changes(
        request, payload.model_dump(exclude={"equipment"}), equipment_quantities(payload)
    )
    await session.commit()
    return request


async def delete_request(session: AsyncSession, request_id: int, office_id: int) -> None:
    request = await get_request(session, request_id, office_id)

    assignments, events = await requests_repository.count_request_usages(session, request_id)
    if assignments or events:
        raise RequestInUseError(
            f"Заявку №{request_id} нельзя удалить: она используется в планах ({assignments}) "
            f"и событиях перепланирования ({events})"
        )

    await requests_repository.delete_request(session, request)
    await session.commit()


async def set_requests_active(
    session: AsyncSession, request_ids: list[int], is_active: bool, office_id: int
) -> RequestActivityReport:
    """Включает или выключает заявки офиса. Если хоть одной нет — не меняет ничего."""
    unique_ids = list(dict.fromkeys(request_ids))
    existing_by_id = {
        request_id: request
        for request_id, request in (
            await requests_repository.get_requests_by_ids(session, unique_ids)
        ).items()
        if request.office_id == office_id
    }

    missing_ids = [request_id for request_id in unique_ids if request_id not in existing_by_id]
    if missing_ids:
        listed = ", ".join(f"№{request_id}" for request_id in missing_ids)
        raise RequestNotFoundError(f"Не найдены заявки: {listed}")

    for request in existing_by_id.values():
        requests_repository.apply_changes(request, {"is_active": is_active})
    await session.commit()
    return RequestActivityReport(updated=len(unique_ids))


async def export_requests_csv(
    session: AsyncSession, office_id: int, plan_date: date | None = None
) -> str:
    """Заявки офиса за день в CSV — слепок дня, который можно загрузить обратно или в другой день."""
    requests = await list_requests(session, office_id, plan_date)
    references = await load_reference_names(session)
    timezone = local_timezone()
    return build_requests_csv(
        [
            {
                "id": request.id,
                "адрес": request.address,
                "широта": f"{float(request.latitude):.6f}",
                "долгота": f"{float(request.longitude):.6f}",
                "тип_работ": (
                    references["work_types"].get(request.work_type_id, "")
                    if request.work_type_id is not None
                    else ""
                ),
                "длительность_мин": request.duration_minutes,
                "окно_начало": format_datetime(request.window_start, timezone),
                "окно_конец": format_datetime(request.window_end, timezone),
                "приоритет": references["priorities"].get(request.priority_id, ""),
                "навык": references["skills"].get(request.skill_id, ""),
                "транспорт": (
                    references["transports"].get(request.transport_id, "")
                    if request.transport_id is not None
                    else ""
                ),
                "активна": "да" if request.is_active else "нет",
                "оборудование": ", ".join(
                    f"{references['equipment'].get(item.equipment_id, item.equipment_id)}: "
                    f"{item.quantity}"
                    for item in request.equipment
                ),
            }
            for request in requests
        ]
    )


async def load_reference_names(session: AsyncSession) -> dict[str, dict[int, str]]:
    """Названия справочников по номеру — для выгрузки в CSV."""
    return {
        "skills": {
            skill.id: skill.name for skill in await references_repository.list_skills(session)
        },
        "priorities": {
            priority.id: priority.name
            for priority in await references_repository.list_priorities(session)
        },
        "transports": {
            transport.id: transport.name
            for transport in await references_repository.list_transports(session)
        },
        "work_types": {
            work_type.id: work_type.name
            for work_type in await references_repository.list_work_types(session)
        },
        "equipment": {
            equipment.id: equipment.name
            for equipment in await references_repository.list_equipment(session)
        },
    }


def moved_to_day(moment: datetime, plan_date: date, day_offset: int) -> datetime:
    """Тот же час и минуты, но в выбранном дне (плюс day_offset суток для окон через полночь)."""
    local = moment.astimezone(local_timezone())
    return local.replace(year=plan_date.year, month=plan_date.month, day=plan_date.day) + timedelta(
        days=day_offset
    )


def copy_rows_to_day(rows: list[dict], plan_date: date) -> None:
    """Переносит разобранные строки в выбранный день: время суток то же, номера новые.

    Так слепок одного дня превращается в самостоятельную копию на другой день,
    а не перезаписывает исходные заявки.
    """
    timezone = local_timezone()
    for fields in rows:
        start, end = fields["window_start"], fields["window_end"]
        day_offset = (end.astimezone(timezone).date() - start.astimezone(timezone).date()).days
        fields["window_start"] = moved_to_day(start, plan_date, 0)
        fields["window_end"] = moved_to_day(end, plan_date, day_offset)
        fields["id"] = None


async def import_requests_csv(
    session: AsyncSession, content: bytes, office_id: int, plan_date: date | None = None
) -> RequestImportReport:
    """Загружает заявки из CSV одной транзакцией.

    Если хоть одна строка с ошибкой — не сохраняется ничего, диспетчер получает список
    ошибок с номерами строк. Заявка с уже существующим номером обновляется, без номера
    или с новым номером — добавляется.

    Если указан plan_date, файл переносится в этот день копией: время суток сохраняется,
    даты заменяются, номера выдаются новые.
    """
    await requests_repository.lock_request_ids(session)
    references = await load_reference_lookup(session)
    parsed = parse_requests_csv(content, references, local_timezone())
    if parsed.errors:
        raise RequestDataError(parsed.errors)
    if not parsed.rows:
        raise RequestDataError(["в файле нет ни одной заявки"])

    if plan_date is not None:
        copy_rows_to_day(parsed.rows, plan_date)

    ids_in_file = [row["id"] for row in parsed.rows if row["id"] is not None]
    existing_by_id = await requests_repository.get_requests_by_ids(session, ids_in_file)
    # номер из файла совпал с заявкой другого офиса — не трогаем её и не пишем поверх
    foreign = sorted(
        request_id
        for request_id, request in existing_by_id.items()
        if request.office_id != office_id
    )
    if foreign:
        listed = ", ".join(f"№{request_id}" for request_id in foreign)
        raise RequestDataError(
            [f"заявки {listed} уже есть в другом офисе — уберите номера или укажите другие"]
        )

    # номера строк без номера подбираем заранее: они не должны совпасть ни с занятыми
    # в БД, ни с явными номерами из файла, ни друг с другом
    taken_ids = await requests_repository.list_request_ids(session)
    taken_ids.update(ids_in_file)

    created = 0
    updated = 0
    for fields in parsed.rows:
        existing_request = existing_by_id.get(fields["id"])
        fields_without_id = {name: value for name, value in fields.items() if name != "id"}
        # оборудование — отдельно; нет колонки в файле — у заявки его не трогаем
        equipment = fields_without_id.pop("equipment", None)

        if existing_request is not None:
            # «активна» в файле не указана — не трогаем: иначе повторная загрузка файла
            # молча включила бы обратно заявки, которые диспетчер выключил
            if fields_without_id["is_active"] is None:
                del fields_without_id["is_active"]
            requests_repository.apply_changes(existing_request, fields_without_id, equipment)
            updated += 1
            continue

        # новая заявка без указанной активности — активна
        if fields_without_id["is_active"] is None:
            fields_without_id["is_active"] = True
        fields_without_id["office_id"] = office_id
        identifier = fields["id"] if fields["id"] is not None else smallest_free_id(taken_ids)
        taken_ids.add(identifier)
        fields_without_id["id"] = identifier
        requests_repository.add_request(session, fields_without_id, equipment)
        created += 1

    await session.flush()
    await session.commit()
    return RequestImportReport(created=created, updated=updated)


async def load_reference_lookup(session: AsyncSession) -> ReferenceLookup:
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    work_types = await references_repository.list_work_types(session)
    equipment = await references_repository.list_equipment(session)
    return ReferenceLookup(
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
        priorities=reference_options([(priority.id, priority.name) for priority in priorities]),
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
        work_types=reference_options([(work_type.id, work_type.name) for work_type in work_types]),
        equipment=reference_options([(item.id, item.name) for item in equipment]),
        work_type_norms={
            work_type.id: WorkTypeNorm(
                skill_id=work_type.skill_id, work_minutes=work_type.work_minutes
            )
            for work_type in work_types
        },
    )


def equipment_quantities(payload: RequestWrite) -> dict[int, int]:
    return {item.equipment_id: item.quantity for item in payload.equipment}


async def apply_work_type_norms(session: AsyncSession, payload: RequestWrite) -> None:
    """Подставляет в заявку нормативы типа работ и проверяет, что длительность и навык заданы.

    Навык определяется типом работ: отдельно его выбирать незачем, иначе два поля об одном
    и том же разъезжаются. Длительность работ на месте берётся из норматива, но её можно
    задать своей: заявка бывает тяжелее норматива.
    """
    references = await load_reference_lookup(session)
    norm = (
        references.work_type_norms.get(payload.work_type_id)
        if payload.work_type_id is not None
        else None
    )
    if norm is not None:
        payload.skill_id = norm.skill_id
        if payload.duration_minutes is None:
            payload.duration_minutes = norm.work_minutes

    problems = []
    if payload.duration_minutes is None:
        problems.append("укажите длительность работ или выберите тип работ")
    if payload.skill_id is None:
        problems.append("укажите навык или выберите тип работ")
    if problems:
        raise RequestDataError(problems)


async def check_references_exist(session: AsyncSession, payload: RequestWrite) -> None:
    """Проверяет, что приоритет, навык, транспорт, тип работ и оборудование есть в справочниках."""
    references = await load_reference_lookup(session)
    problems = []
    if str(payload.priority_id) not in references.priorities.id_by_key:
        problems.append(f"приоритета №{payload.priority_id} нет в справочнике")
    if payload.skill_id is not None and str(payload.skill_id) not in references.skills.id_by_key:
        problems.append(f"навыка №{payload.skill_id} нет в справочнике")
    if (
        payload.work_type_id is not None
        and str(payload.work_type_id) not in references.work_types.id_by_key
    ):
        problems.append(f"типа работ №{payload.work_type_id} нет в справочнике")
    if (
        payload.transport_id is not None
        and str(payload.transport_id) not in references.transports.id_by_key
    ):
        problems.append(f"транспорта №{payload.transport_id} нет в справочнике")
    missing_equipment = [
        item.equipment_id
        for item in payload.equipment
        if str(item.equipment_id) not in references.equipment.id_by_key
    ]
    if missing_equipment:
        listed = ", ".join(f"№{equipment_id}" for equipment_id in missing_equipment)
        problems.append(f"оборудования {listed} нет в справочнике")
    if problems:
        raise RequestDataError(problems)
