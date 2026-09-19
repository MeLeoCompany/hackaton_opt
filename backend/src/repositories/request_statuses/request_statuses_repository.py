"""Статусы заявок и допустимые переходы — чтение справочников."""

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    AppUser,
    Assignment,
    Plan,
    Request,
    RequestStatus,
    RequestStatusHistory,
    RequestStatusTransition,
)


async def list_statuses(session: AsyncSession) -> list[RequestStatus]:
    result = await session.execute(select(RequestStatus).order_by(RequestStatus.id))
    return list(result.scalars().all())


async def list_transitions(session: AsyncSession) -> list[RequestStatusTransition]:
    result = await session.execute(
        select(RequestStatusTransition).order_by(
            RequestStatusTransition.from_status_id, RequestStatusTransition.to_status_id
        )
    )
    return list(result.scalars().all())


def plannable_status_ids():
    """Подзапрос: статусы, заявки в которых идут в расчёт плана."""
    return select(RequestStatus.id).where(RequestStatus.plannable.is_(True))


def add_history(
    session: AsyncSession,
    request_ids: list[int],
    from_status_id: int | None,
    to_status_id: int,
    *,
    manual: bool,
    user_id: int | None = None,
    plan_id: int | None = None,
    comment: str = "",
) -> None:
    """Записывает одну и ту же смену статуса для нескольких заявок."""
    for request_id in request_ids:
        session.add(
            RequestStatusHistory(
                request_id=request_id,
                from_status_id=from_status_id,
                to_status_id=to_status_id,
                manual=manual,
                user_id=user_id,
                plan_id=plan_id,
                comment=comment,
            )
        )


async def list_history(
    session: AsyncSession, request_id: int
) -> list[tuple[RequestStatusHistory, str | None]]:
    """История заявки по порядку, с именем того, кто менял статус."""
    result = await session.execute(
        select(RequestStatusHistory, AppUser.name)
        .outerjoin(AppUser, AppUser.id == RequestStatusHistory.user_id)
        .where(RequestStatusHistory.request_id == request_id)
        .order_by(RequestStatusHistory.changed_at, RequestStatusHistory.id)
    )
    return [(entry, user_name) for entry, user_name in result.all()]


async def list_routes_of(session: AsyncSession, requests: list[Request]) -> list[list[Request]]:
    """Маршруты бригад утверждённых планов, в которых стоят эти заявки: заявки по порядку визитов."""
    held = [
        (request.approved_plan_id, request.id) for request in requests if request.approved_plan_id
    ]
    if not held:
        return []
    keys = await session.execute(
        select(Assignment.plan_id, Assignment.engineer_id)
        .where(
            tuple_(Assignment.plan_id, Assignment.request_id).in_(held),
            Assignment.engineer_id.is_not(None),
        )
        .distinct()
    )
    routes = []
    for plan_id, engineer_id in keys.all():
        result = await session.execute(
            select(Request)
            .join(Assignment, Assignment.request_id == Request.id)
            .where(
                Assignment.plan_id == plan_id,
                Assignment.engineer_id == engineer_id,
                # снятая с плана заявка («Новая», ждёт пересчёта) бригаду не держит
                Request.approved_plan_id == plan_id,
            )
            .order_by(Assignment.visit_order)
        )
        routes.append(list(result.scalars().all()))
    return routes


async def list_placed_in_approved_plan(session: AsyncSession, requests: list[Request]) -> set[int]:
    """Какие из заявок стоят в маршруте бригады своего плана и этот план всё ещё утверждён.

    Только такую отменённую заявку можно вернуть «В план» без пересчёта: её место в маршруте цело.
    """
    held = [
        (request.approved_plan_id, request.id) for request in requests if request.approved_plan_id
    ]
    if not held:
        return set()
    result = await session.execute(
        select(Assignment.request_id)
        .join(Plan, Plan.id == Assignment.plan_id)
        .where(
            tuple_(Assignment.plan_id, Assignment.request_id).in_(held),
            Assignment.engineer_id.is_not(None),
            Plan.approved_at.is_not(None),
            Plan.superseded_at.is_(None),
        )
    )
    return set(result.scalars().all())
