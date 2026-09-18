"""Чтение и запись планов и назначений. Коммит делает сервис — здесь только запросы."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Assignment, Plan, PlanRunType, Request


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
        )
    )
    return result.scalar_one_or_none()


async def hold_plan_requests(
    session: AsyncSession, plan: Plan, approved_at: datetime
) -> tuple[int, int]:
    """Утверждает план и закрепляет за ним назначенные заявки.

    Закреплённую заявку не возьмут планы других дней: иначе заявка с окном через полночь
    выполнялась бы дважды — в плане вчерашнего и в плане сегодняшнего дня. Уже закреплённые
    другим планом заявки не перезаписываются; вызывающий код сравнивает два счётчика и при
    расхождении откатывает всю транзакцию.
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
    result = await session.execute(
        update(Request)
        .where(
            Request.id.in_(assigned),
            or_(Request.approved_plan_id.is_(None), Request.approved_plan_id == plan.id),
        )
        .values(approved_plan_id=plan.id)
    )
    held_count = result.rowcount or 0
    if held_count == assigned_count:
        plan.approved_at = approved_at
    return held_count, assigned_count


async def release_plan_requests(session: AsyncSession, plan: Plan) -> int:
    """Снимает утверждение плана и отпускает его заявки другим дням."""
    plan.approved_at = None
    result = await session.execute(
        update(Request).where(Request.approved_plan_id == plan.id).values(approved_plan_id=None)
    )
    return result.rowcount or 0


async def list_plan_assignments(session: AsyncSession, plan_id: int) -> list[Assignment]:
    """Назначения плана вместе с заявкой и исполнителем."""
    result = await session.execute(
        select(Assignment)
        .options(selectinload(Assignment.request), selectinload(Assignment.engineer))
        .where(Assignment.plan_id == plan_id)
        .order_by(Assignment.engineer_id, Assignment.visit_order, Assignment.request_id)
    )
    return list(result.scalars().all())


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
