"""Чтение и запись планов и назначений. Коммит делает сервис — здесь только запросы."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import (
    Assignment,
    Plan,
    PlanRoute,
    PlanRunType,
    Request,
    RequestFact,
    RequestStatusId,
)


def add_plan(
    session: AsyncSession,
    run_type: PlanRunType,
    plan_date: date,
    solver: str,
    *,
    office_id: int,
    solve_duration_ms: Decimal | None = None,
    objective_policy: dict | None = None,
) -> Plan:
    plan = Plan(
        office_id=office_id,
        run_type=run_type,
        plan_date=plan_date,
        solver=solver,
        solve_duration_ms=solve_duration_ms,
        objective_policy=objective_policy,
    )
    session.add(plan)
    return plan


def add_assignment(session: AsyncSession, fields: dict) -> Assignment:
    assignment = Assignment(**fields)
    session.add(assignment)
    return assignment


async def get_plan(session: AsyncSession, plan_id: int) -> Plan | None:
    return await session.get(Plan, plan_id)


async def delete_plan(session: AsyncSession, plan: Plan) -> None:
    """Удаляет план; назначения уходят вместе с ним по ON DELETE CASCADE."""
    await session.delete(plan)


async def list_plans(
    session: AsyncSession, plan_date: date | None, *, office_id: int
) -> list[Plan]:
    """Планы офиса, новые первыми; если указан день — только на этот день."""
    query = (
        select(Plan)
        .where(Plan.office_id == office_id)
        .order_by(Plan.created_at.desc(), Plan.id.desc())
    )
    if plan_date is not None:
        query = query.where(Plan.plan_date == plan_date)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_approved_plan(
    session: AsyncSession, plan_date: date, *, office_id: int
) -> Plan | None:
    """Утверждённый план офиса на день; у офиса на день он может быть только один."""
    result = await session.execute(
        select(Plan).where(
            Plan.office_id == office_id,
            Plan.plan_date == plan_date,
            Plan.approved_at.is_not(None),
            # заменённый утверждённым пересчётом — уже не действующий план дня
            Plan.superseded_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def hold_plan_requests(
    session: AsyncSession, plan: Plan, approved_at: datetime
) -> tuple[int, int, list[int]]:
    """Утверждает план и закрепляет за ним назначенные заявки: «Новая» -> «В плане».

    Закреплённую заявку не возьмут планы других дней: иначе заявка с окном через полночь
    выполнялась бы дважды — в плане вчерашнего и в плане сегодняшнего дня. Выполненные,
    отменённые, взятые в работу и занятые другим планом заявки не трогаются; вызывающий код
    сравнивает счётчики и при расхождении откатывает всю транзакцию.

    Возвращает: сколько заявок закреплено, сколько назначено в плане, какие перешли
    в «В плане» сейчас (для истории статусов).
    """
    assigned = (
        select(Assignment.request_id)
        .where(Assignment.plan_id == plan.id, Assignment.engineer_id.is_not(None))
        .scalar_subquery()
    )
    assigned_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(
                Assignment.plan_id == plan.id,
                Assignment.engineer_id.is_not(None),
            )
        )
        or 0
    )
    already_held = int(
        await session.scalar(
            select(func.count())
            .select_from(Request)
            .where(
                Request.id.in_(assigned),
                Request.approved_plan_id == plan.id,
                Request.status_id == RequestStatusId.PLANNED,
            )
        )
        or 0
    )
    result = await session.execute(
        update(Request)
        .where(
            Request.id.in_(assigned),
            Request.approved_plan_id.is_(None),
            Request.status_id == RequestStatusId.NEW,
        )
        .values(approved_plan_id=plan.id, status_id=RequestStatusId.PLANNED)
        .returning(Request.id)
        .execution_options(synchronize_session=False)
    )
    planned_ids = list(result.scalars().all())
    held_count = already_held + len(planned_ids)
    if held_count == assigned_count:
        plan.approved_at = approved_at
    return held_count, assigned_count, planned_ids


async def release_plan_requests(session: AsyncSession, plan: Plan) -> list[int]:
    """Снимает утверждение плана: заявки «В плане» снова «Новые» и свободны для других дней.

    Взятые в работу, выполненные и отменённые остаются как есть и сохраняют ссылку на план:
    по ней видно, по какому плану бригада их выполняет или выполнила.
    Возвращает заявки, вернувшиеся в «Новые» (для истории статусов).
    """
    plan.approved_at = None
    result = await session.execute(
        update(Request)
        .where(
            Request.approved_plan_id == plan.id,
            Request.status_id == RequestStatusId.PLANNED,
        )
        .values(approved_plan_id=None, status_id=RequestStatusId.NEW)
        .returning(Request.id)
        .execution_options(synchronize_session=False)
    )
    return list(result.scalars().all())


async def list_plan_assignments(session: AsyncSession, plan_id: int) -> list[Assignment]:
    """Назначения плана вместе с заявкой и исполнителем."""
    result = await session.execute(
        select(Assignment)
        .options(selectinload(Assignment.request), selectinload(Assignment.engineer))
        .where(Assignment.plan_id == plan_id)
        .order_by(Assignment.engineer_id, Assignment.visit_order, Assignment.request_id)
    )
    return list(result.scalars().all())


async def delete_assignments(session: AsyncSession, plan_id: int, request_ids: set[int]) -> int:
    """Убрать заявки из плана: перенесённые и отменённые в нём больше не числятся."""
    if not request_ids:
        return 0
    result = await session.execute(
        delete(Assignment).where(
            Assignment.plan_id == plan_id, Assignment.request_id.in_(request_ids)
        )
    )
    return result.rowcount or 0


async def count_assignments_by_plan(
    session: AsyncSession, plan_ids: list[int]
) -> dict[int, tuple[int, int, int]]:
    """{план: (задействовано исполнителей, назначено заявок, не назначено заявок)}."""
    if not plan_ids:
        return {}
    rows = await session.execute(
        select(
            Assignment.plan_id,
            func.count(func.distinct(Assignment.engineer_id)),
            func.count(Assignment.engineer_id),
            func.count(),
        )
        .where(Assignment.plan_id.in_(plan_ids))
        .group_by(Assignment.plan_id)
    )
    return {
        plan_id: (engineers_used, assigned, total - assigned)
        for plan_id, engineers_used, assigned, total in rows
    }


async def assigned_request_ids_by_plan(
    session: AsyncSession, plan_ids: list[int]
) -> dict[int, set[int]]:
    if not plan_ids:
        return {}
    rows = await session.execute(
        select(Assignment.plan_id, Assignment.request_id).where(
            Assignment.plan_id.in_(plan_ids), Assignment.engineer_id.is_not(None)
        )
    )
    result: dict[int, set[int]] = {}
    for plan_id, request_id in rows:
        result.setdefault(plan_id, set()).add(request_id)
    return result


async def list_withdrawn_requests(session: AsyncSession, plan_id: int) -> list[tuple[int, int]]:
    """Заявки из маршрутов утверждённого плана, которых в нём больше нет: отменены или
    возвращены в «Новая» (тогда за планом они уже не закреплены). [(номер, статус)]"""
    result = await session.execute(
        select(Assignment.request_id, Request.status_id)
        .join(Request, Request.id == Assignment.request_id)
        .where(
            Assignment.plan_id == plan_id,
            Assignment.engineer_id.is_not(None),
            (Request.status_id == RequestStatusId.CANCELLED)
            | Request.approved_plan_id.is_distinct_from(plan_id),
        )
        .order_by(Assignment.request_id)
    )
    return [(request_id, status_id) for request_id, status_id in result.all()]


async def plan_request_ids(session: AsyncSession, plan_id: int) -> set[int]:
    """Все заявки, которые видел расчёт плана: назначенные и неназначенные."""
    result = await session.execute(
        select(Assignment.request_id).where(Assignment.plan_id == plan_id)
    )
    return set(result.scalars().all())


async def list_bound_requests(session: AsyncSession, plan_id: int) -> list[Request]:
    """Заявки, закреплённые за утверждённым планом (request.approved_plan_id)."""
    result = await session.execute(
        select(Request).where(Request.approved_plan_id == plan_id).order_by(Request.id)
    )
    return list(result.scalars().all())


async def has_brigade_marks(session: AsyncSession, plan_id: int) -> bool:
    """Отмечалась ли хоть одна бригада по заявкам этого плана: выехала, прибыла, закрыла."""
    result = await session.execute(
        select(RequestFact.request_id)
        .join(Assignment, Assignment.request_id == RequestFact.request_id)
        .where(Assignment.plan_id == plan_id)
    )
    return result.first() is not None


async def approved_replan_of(session: AsyncSession, plan_ids: list[int]) -> dict[int, int]:
    """Какой утверждённый пересчёт заменил каждый из планов: id родителя -> id пересчёта."""
    if not plan_ids:
        return {}
    result = await session.execute(
        select(Plan.parent_plan_id, Plan.id).where(
            Plan.parent_plan_id.in_(plan_ids), Plan.approved_at.is_not(None)
        )
    )
    return {parent_id: plan_id for parent_id, plan_id in result.all()}


async def pending_replan_of(session: AsyncSession, plan_ids: list[int]) -> dict[int, int]:
    """Посчитанный, но ещё не вступивший в силу пересчёт: id родителя -> id пересчёта.

    Он вступит в силу сам, в момент, на который посчитан; до тех пор выезд закрыт туда, куда он
    бригаду не ведёт (departure_gate). Недействительный пересчёт сюда не попадает: он уже
    никого не держит. Если пересчётов несколько, берётся последний.
    """
    if not plan_ids:
        return {}
    result = await session.execute(
        select(Plan.parent_plan_id, Plan.id)
        .where(
            Plan.parent_plan_id.in_(plan_ids),
            Plan.approved_at.is_(None),
            Plan.voided_at.is_(None),
        )
        .order_by(Plan.id)
    )
    return {parent_id: plan_id for parent_id, plan_id in result.all()}


async def voided_replan_of(session: AsyncSession, plan_ids: list[int]) -> dict[int, Plan]:
    """Пересчёт, который не вступил в силу: id родителя -> сам пересчёт с причиной."""
    if not plan_ids:
        return {}
    result = await session.execute(
        select(Plan)
        .where(Plan.parent_plan_id.in_(plan_ids), Plan.voided_at.is_not(None))
        .order_by(Plan.id)
    )
    return {plan.parent_plan_id: plan for plan in result.scalars().all()}


async def due_replans(session: AsyncSession, moment: datetime) -> list[Plan]:
    """Пересчёты, которым пора вступать в силу: их момент выезда уже настал."""
    result = await session.execute(
        select(Plan)
        .where(
            Plan.parent_plan_id.is_not(None),
            Plan.approved_at.is_(None),
            Plan.voided_at.is_(None),
            Plan.replanned_at.is_not(None),
            Plan.replanned_at <= moment,
        )
        .order_by(Plan.id)
    )
    return list(result.scalars().all())


async def unapproved_replan_id(session: AsyncSession, plan_id: int) -> int | None:
    """Посчитанный, но не утверждённый пересчёт плана (docs/algoV2.md, шаг 8)."""
    result = await session.execute(
        select(Plan.id).where(
            Plan.parent_plan_id == plan_id,
            Plan.approved_at.is_(None),
            Plan.voided_at.is_(None),
        )
    )
    row = result.first()
    return row[0] if row else None


async def list_cached_routes(session: AsyncSession, plan_id: int) -> dict[int, PlanRoute]:
    """Уже построенные маршруты плана — по бригадам (db/init/042)."""
    result = await session.execute(select(PlanRoute).where(PlanRoute.plan_id == plan_id))
    return {route.engineer_id: route for route in result.scalars().all()}


async def save_cached_route(
    session: AsyncSession, plan_id: int, engineer_id: int, fingerprint: str, travel: dict
) -> None:
    """Запоминает построенный маршрут: следующее открытие плана возьмёт его отсюда."""
    await session.merge(
        PlanRoute(plan_id=plan_id, engineer_id=engineer_id, fingerprint=fingerprint, travel=travel)
    )
