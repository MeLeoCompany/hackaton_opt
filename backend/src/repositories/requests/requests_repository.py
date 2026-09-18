"""Чтение и запись заявок в БД. Коммит делает сервис — здесь только запросы."""

from datetime import date, datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Assignment, Event, Plan, Request

# Shared by request creation and CSV import; independent from engineer ID allocation.
REQUEST_ID_LOCK_KEY = 7419821


async def list_requests(session: AsyncSession) -> list[Request]:
    """Все заявки, ближайшие по времени окна — первыми."""
    result = await session.execute(select(Request).order_by(Request.window_start, Request.id))
    return list(result.scalars().all())


async def list_requests_in_period(
    session: AsyncSession, period_start: datetime, period_end: datetime
) -> list[Request]:
    """Заявки (и выключенные тоже), окно которых пересекается с периодом [period_start, period_end)."""
    result = await session.execute(
        select(Request)
        .where(Request.window_start < period_end, Request.window_end > period_start)
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def list_active_requests(session: AsyncSession) -> list[Request]:
    result = await session.execute(
        select(Request)
        .where(Request.is_active.is_(True))
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def list_active_requests_in_period(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    plan_date: date | None = None,
) -> list[Request]:
    """Активные заявки, окно которых пересекается с периодом [period_start, period_end).

    Если указан plan_date, заявки, закреплённые за утверждённым планом другого дня,
    не возвращаются: они уже распределены и второй раз выполняться не должны.
    """
    query = (
        select(Request)
        .where(
            Request.is_active.is_(True),
            Request.window_start < period_end,
            Request.window_end > period_start,
        )
        .order_by(Request.input_order)
    )
    if plan_date is not None:
        query = query.outerjoin(Plan, Plan.id == Request.approved_plan_id).where(
            or_(Request.approved_plan_id.is_(None), Plan.plan_date == plan_date)
        )
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_requests_held_by_other_days(
    session: AsyncSession, period_start: datetime, period_end: datetime, plan_date: date
) -> list[tuple[Request, Plan]]:
    """Заявки дня, закреплённые за утверждённым планом другого дня, вместе с этим планом.

    Нужны, чтобы предупредить диспетчера перед расчётом: часть заявок в план не попадёт.
    """
    result = await session.execute(
        select(Request, Plan)
        .join(Plan, Plan.id == Request.approved_plan_id)
        .where(
            Request.is_active.is_(True),
            Request.window_start < period_end,
            Request.window_end > period_start,
            Plan.plan_date != plan_date,
        )
        .order_by(Request.input_order)
    )
    return [(request, plan) for request, plan in result.all()]


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


async def list_request_ids(session: AsyncSession) -> set[int]:
    """Номера всех заявок — из них выбирается номер для новой."""
    result = await session.execute(select(Request.id))
    return set(result.scalars().all())


async def lock_request_ids(session: AsyncSession) -> None:
    """Serialize API inserts/imports until the transaction ends."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": REQUEST_ID_LOCK_KEY})
