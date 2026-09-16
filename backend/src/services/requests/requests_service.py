"""Заявки: просмотр, создание, изменение, удаление и загрузка из CSV."""

from datetime import date

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
    parse_requests_csv,
    reference_options,
)


class RequestNotFoundError(NotFoundError):
    """Заявки с таким номером нет."""


class RequestInUseError(InUseError):
    """Заявку нельзя удалить: на неё ссылаются планы или события перепланирования."""


class RequestDataError(DataError):
    """Данные заявки не прошли проверку."""


async def list_requests(session: AsyncSession, plan_date: date | None = None) -> list[Request]:
    """Все заявки или только те, чьё окно попадает в выбранный день."""
    if plan_date is None:
        return await requests_repository.list_requests(session)
    day_start, day_end = day_bounds(plan_date)
    return await requests_repository.list_requests_in_period(session, day_start, day_end)


async def get_request(session: AsyncSession, request_id: int) -> Request:
    request = await requests_repository.get_request(session, request_id)
    if request is None:
        raise RequestNotFoundError(f"Заявка №{request_id} не найдена")
    return request


async def create_request(session: AsyncSession, payload: RequestCreate) -> Request:
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

    fields = payload.model_dump()
    if fields["id"] is None:
        fields["id"] = smallest_free_id(await requests_repository.list_request_ids(session))

    request = requests_repository.add_request(session, fields)
    await session.flush()
    await session.commit()
    return request


async def update_request(session: AsyncSession, request_id: int, payload: RequestWrite) -> Request:
    request = await get_request(session, request_id)
    await check_references_exist(session, payload)
    await apply_work_type_norms(session, payload)
    requests_repository.apply_changes(request, payload.model_dump())
    await session.commit()
    return request


async def delete_request(session: AsyncSession, request_id: int) -> None:
    request = await get_request(session, request_id)

    assignments, events = await requests_repository.count_request_usages(session, request_id)
    if assignments or events:
        raise RequestInUseError(
            f"Заявку №{request_id} нельзя удалить: она используется в планах ({assignments}) "
            f"и событиях перепланирования ({events})"
        )

    await requests_repository.delete_request(session, request)
    await session.commit()


async def set_requests_active(
    session: AsyncSession, request_ids: list[int], is_active: bool
) -> RequestActivityReport:
    """Включает или выключает заявки для планирования. Если хоть одной нет — не меняет ничего."""
    unique_ids = list(dict.fromkeys(request_ids))
    existing_by_id = await requests_repository.get_requests_by_ids(session, unique_ids)

    missing_ids = [request_id for request_id in unique_ids if request_id not in existing_by_id]
    if missing_ids:
        listed = ", ".join(f"№{request_id}" for request_id in missing_ids)
        raise RequestNotFoundError(f"Не найдены заявки: {listed}")

    for request in existing_by_id.values():
        requests_repository.apply_changes(request, {"is_active": is_active})
    await session.commit()
    return RequestActivityReport(updated=len(unique_ids))


async def import_requests_csv(session: AsyncSession, content: bytes) -> RequestImportReport:
    """Загружает заявки из CSV одной транзакцией.

    Если хоть одна строка с ошибкой — не сохраняется ничего, диспетчер получает список
    ошибок с номерами строк. Заявка с уже существующим номером обновляется, без номера
    или с новым номером — добавляется.
    """
    await requests_repository.lock_request_ids(session)
    references = await load_reference_lookup(session)
    parsed = parse_requests_csv(content, references, local_timezone())
    if parsed.errors:
        raise RequestDataError(parsed.errors)
    if not parsed.rows:
        raise RequestDataError(["в файле нет ни одной заявки"])

    ids_in_file = [row["id"] for row in parsed.rows if row["id"] is not None]
    existing_by_id = await requests_repository.get_requests_by_ids(session, ids_in_file)

    # номера строк без номера подбираем заранее: они не должны совпасть ни с занятыми
    # в БД, ни с явными номерами из файла, ни друг с другом
    taken_ids = await requests_repository.list_request_ids(session)
    taken_ids.update(ids_in_file)

    created = 0
    updated = 0
    for fields in parsed.rows:
        existing_request = existing_by_id.get(fields["id"])
        fields_without_id = {name: value for name, value in fields.items() if name != "id"}

        if existing_request is not None:
            # «активна» в файле не указана — не трогаем: иначе повторная загрузка файла
            # молча включила бы обратно заявки, которые диспетчер выключил
            if fields_without_id["is_active"] is None:
                del fields_without_id["is_active"]
            requests_repository.apply_changes(existing_request, fields_without_id)
            updated += 1
            continue

        # новая заявка без указанной активности — активна
        if fields_without_id["is_active"] is None:
            fields_without_id["is_active"] = True
        identifier = fields["id"] if fields["id"] is not None else smallest_free_id(taken_ids)
        taken_ids.add(identifier)
        fields_without_id["id"] = identifier
        requests_repository.add_request(session, fields_without_id)
        created += 1

    await session.flush()
    await session.commit()
    return RequestImportReport(created=created, updated=updated)


async def load_reference_lookup(session: AsyncSession) -> ReferenceLookup:
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    work_types = await references_repository.list_work_types(session)
    return ReferenceLookup(
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
        priorities=reference_options([(priority.id, priority.name) for priority in priorities]),
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
        work_types=reference_options([(work_type.id, work_type.name) for work_type in work_types]),
        work_type_norms={
            work_type.id: WorkTypeNorm(
                skill_id=work_type.skill_id, work_minutes=work_type.work_minutes
            )
            for work_type in work_types
        },
    )


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
    """Проверяет, что приоритет, навык, транспорт и тип работ заявки есть в справочниках."""
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
    if problems:
        raise RequestDataError(problems)
