"""Чтение и запись заявок в БД. Коммит делает сервис — здесь только запросы."""

from datetime import date, datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Assignment,
    Event,
    Plan,
    Priority,
    Request,
    RequestEquipment,
    RequestStatus,
)
from src.repositories.request_statuses.request_statuses_repository import plannable_status_ids

# Shared by request creation and CSV import; independent from engineer ID allocation.
REQUEST_ID_LOCK_KEY = 7419821


async def list_requests(session: AsyncSession, *, office_id: int) -> list[Request]:
    """Все заявки офиса, ближайшие по времени окна — первыми."""
    result = await session.execute(
        select(Request)
        .where(Request.office_id == office_id)
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def list_requests_in_period(
    session: AsyncSession, period_start: datetime, period_end: datetime, *, office_id: int
) -> list[Request]:
    """Заявки офиса (в любом статусе), окно которых пересекается с [period_start, period_end)."""
    result = await session.execute(
        select(Request)
        .where(
            Request.office_id == office_id,
            Request.window_start < period_end,
            Request.window_end > period_start,
        )
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def list_requests_moved_from(
    session: AsyncSession, plan_date: date, *, office_id: int
) -> list[Request]:
    """Заявки, перенесённые с этого дня: их окно уже в другом дне (docs/algoV2.md, шаг 4)."""
    result = await session.execute(
        select(Request)
        .where(Request.office_id == office_id, Request.moved_from == plan_date)
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def urgent_request_ids(
    session: AsyncSession, request_ids: set[int], top_priority_level: int
) -> set[int]:
    """Какие из этих заявок аварийные — по справочнику приоритетов.

    Нужно планам, которые видели заявку не в своём расчёте: пересчёт берёт выполненные
    и начатые заявки из прежнего плана, и в его снимке данных их нет.
    """
    if not request_ids:
        return set()
    result = await session.execute(
        select(Request.id)
        .join(Priority, Priority.id == Request.priority_id)
        .where(Request.id.in_(request_ids), Priority.level == top_priority_level)
    )
    return set(result.scalars().all())


async def list_active_requests(session: AsyncSession, *, office_id: int) -> list[Request]:
    result = await session.execute(
        select(Request)
        .where(Request.office_id == office_id, Request.status_id.in_(plannable_status_ids()))
        .order_by(Request.window_start, Request.id)
    )
    return list(result.scalars().all())


async def list_active_requests_in_period(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    plan_date: date | None = None,
    *,
    office_id: int,
) -> list[Request]:
    """Заявки офиса, идущие в планирование (по статусу), окно которых пересекается с периодом.

    Если указан plan_date, заявки, закреплённые за утверждённым планом другого дня,
    не возвращаются: они уже распределены и второй раз выполняться не должны.
    """
    query = (
        select(Request)
        .where(
            Request.office_id == office_id,
            Request.status_id.in_(plannable_status_ids()),
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
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    plan_date: date,
    *,
    office_id: int,
) -> list[tuple[Request, Plan]]:
    """Заявки дня, закреплённые за утверждённым планом другого дня, вместе с этим планом.

    Нужны, чтобы предупредить диспетчера перед расчётом: часть заявок в план не попадёт.
    """
    result = await session.execute(
        select(Request, Plan)
        .join(Plan, Plan.id == Request.approved_plan_id)
        .where(
            Request.office_id == office_id,
            Request.status_id.in_(plannable_status_ids()),
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


def add_request(
    session: AsyncSession,
    fields: dict,
    quantities: dict[int, int] | None = None,
    status: RequestStatus | None = None,
) -> Request:
    """Новая заявка; status — её начальный статус (объект, чтобы ответ API сразу его знал)."""
    request = Request(**fields)
    if status is not None:
        request.status_id = status.id
        request.status = status
    request.equipment = [
        RequestEquipment(equipment_id=equipment_id, quantity=quantity)
        for equipment_id, quantity in (quantities or {}).items()
    ]
    session.add(request)
    return request


def apply_changes(request: Request, fields: dict, quantities: dict[int, int] | None = None) -> None:
    """Меняет поля заявки; quantities=None — требуемое оборудование не трогаем."""
    for field_name, value in fields.items():
        setattr(request, field_name, value)
    if quantities is not None:
        set_equipment(request, quantities)


def set_equipment(request: Request, quantities: dict[int, int]) -> None:
    """Требование заявки -> {тип: количество}. Существующие строки меняются на месте:
    удалить и тут же вставить строку с тем же ключом в одной транзакции нельзя."""
    kept = []
    for item in request.equipment:
        if item.equipment_id in quantities:
            item.quantity = quantities[item.equipment_id]
            kept.append(item)
    known = {item.equipment_id for item in kept}
    kept += [
        RequestEquipment(equipment_id=equipment_id, quantity=quantity)
        for equipment_id, quantity in quantities.items()
        if equipment_id not in known
    ]
    request.equipment = kept


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
