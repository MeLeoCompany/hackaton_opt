"""Заявки: просмотр, создание, изменение, удаление и загрузка из CSV."""

from datetime import timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
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
    parse_requests_csv,
    reference_options,
)


class RequestNotFoundError(Exception):
    """Заявки с таким номером нет."""


class RequestInUseError(Exception):
    """Заявку нельзя удалить: на неё ссылаются планы или события перепланирования."""


class RequestDataError(Exception):
    """Данные заявки не прошли проверку. messages — понятные диспетчеру причины."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


def local_timezone() -> timezone:
    return timezone(timedelta(hours=settings.local_utc_offset_hours))


async def list_requests(session: AsyncSession) -> list[Request]:
    return await requests_repository.list_requests(session)


async def get_request(session: AsyncSession, request_id: int) -> Request:
    request = await requests_repository.get_request(session, request_id)
    if request is None:
        raise RequestNotFoundError(f"Заявка №{request_id} не найдена")
    return request


async def create_request(session: AsyncSession, payload: RequestCreate) -> Request:
    await check_references_exist(session, payload)

    if payload.id is not None and await requests_repository.get_request(session, payload.id) is not None:
        raise RequestDataError(
            [f"заявка №{payload.id} уже существует — измените её или укажите другой номер"]
        )

    fields = payload.model_dump()
    if fields["id"] is None:
        del fields["id"]

    request = requests_repository.add_request(session, fields)
    await session.flush()
    if payload.id is not None:
        await requests_repository.sync_request_id_sequence(session)
    await session.commit()
    return request


async def update_request(session: AsyncSession, request_id: int, payload: RequestWrite) -> Request:
    request = await get_request(session, request_id)
    await check_references_exist(session, payload)
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
    references = await load_reference_lookup(session)
    parsed = parse_requests_csv(content, references, local_timezone())
    if parsed.errors:
        raise RequestDataError(parsed.errors)
    if not parsed.rows:
        raise RequestDataError(["в файле нет ни одной заявки"])

    ids_in_file = [row["id"] for row in parsed.rows if row["id"] is not None]
    existing_by_id = await requests_repository.get_requests_by_ids(session, ids_in_file)

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
        if fields["id"] is not None:
            fields_without_id["id"] = fields["id"]
        requests_repository.add_request(session, fields_without_id)
        created += 1

    await session.flush()
    if ids_in_file:
        await requests_repository.sync_request_id_sequence(session)
    await session.commit()
    return RequestImportReport(created=created, updated=updated)


async def load_reference_lookup(session: AsyncSession) -> ReferenceLookup:
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    return ReferenceLookup(
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
        priorities=reference_options([(priority.id, priority.name) for priority in priorities]),
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
    )


async def check_references_exist(session: AsyncSession, payload: RequestWrite) -> None:
    """Проверяет, что приоритет, навык и транспорт заявки есть в справочниках."""
    references = await load_reference_lookup(session)
    problems = []
    if str(payload.priority_id) not in references.priorities.id_by_key:
        problems.append(f"приоритета №{payload.priority_id} нет в справочнике")
    if str(payload.skill_id) not in references.skills.id_by_key:
        problems.append(f"навыка №{payload.skill_id} нет в справочнике")
    if payload.transport_id is not None and str(payload.transport_id) not in references.transports.id_by_key:
        problems.append(f"транспорта №{payload.transport_id} нет в справочнике")
    if problems:
        raise RequestDataError(problems)
