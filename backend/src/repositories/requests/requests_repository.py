"""Чтение и запись заявок в БД. Коммит делает сервис — здесь только запросы."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Assignment, Event, Request


async def list_requests(session: AsyncSession) -> list[Request]:
    """Все заявки, ближайшие по времени окна — первыми."""
    result = await session.execute(select(Request).order_by(Request.window_start, Request.id))
    return list(result.scalars().all())


async def get_request(session: AsyncSession, request_id: int) -> Request | None:
    return await session.get(Request, request_id)


async def get_requests_by_ids(session: AsyncSession, request_ids: list[int]) -> dict[int, Request]:
    """Заявки с указанными номерами, которые уже есть в БД: {номер: заявка}."""
    if not request_ids:
        return {}
    result = await session.execute(select(Request).where(Request.id.in_(request_ids)))
    return {request.id: request for request in result.scalars().all()}


def add_request(session: AsyncSession, fields: dict) -> Request:
    request = Request(**fields)
    session.add(request)
    return request


def apply_changes(request: Request, fields: dict) -> None:
    for field_name, value in fields.items():
        setattr(request, field_name, value)


async def delete_request(session: AsyncSession, request: Request) -> None:
    await session.delete(request)


async def count_request_usages(session: AsyncSession, request_id: int) -> tuple[int, int]:
    """Сколько раз заявка встречается в назначениях планов и в событиях перепланирования."""
    assignments = await session.scalar(
        select(func.count()).select_from(Assignment).where(Assignment.request_id == request_id)
    )
    events = await session.scalar(
        select(func.count()).select_from(Event).where(Event.request_id == request_id)
    )
    return int(assignments or 0), int(events or 0)


async def sync_request_id_sequence(session: AsyncSession) -> None:
    """Сдвигает автонумерацию заявок за самый большой номер в таблице.

    Нужно после вставки заявок с явными номерами: иначе следующая заявка без номера
    получит из автонумерации номер, который уже занят.
    """
    await session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('request', 'id'), "
            "GREATEST((SELECT MAX(id) FROM request), 1))"
        )
    )
