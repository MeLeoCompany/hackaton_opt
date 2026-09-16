"""Чтение и запись планов и назначений. Коммит делает сервис — здесь только запросы."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Assignment, Plan, PlanRunType


def add_plan(session: AsyncSession, run_type: PlanRunType, plan_date: date, solver: str) -> Plan:
    plan = Plan(run_type=run_type, plan_date=plan_date, solver=solver)
    session.add(plan)
    return plan


def add_assignment(session: AsyncSession, fields: dict) -> Assignment:
    assignment = Assignment(**fields)
    session.add(assignment)
    return assignment


async def get_plan(session: AsyncSession, plan_id: int) -> Plan | None:
    return await session.get(Plan, plan_id)


async def list_plans(session: AsyncSession, plan_date: date | None) -> list[Plan]:
    """Планы, новые первыми; если указан день — только на этот день."""
    query = select(Plan).order_by(Plan.created_at.desc(), Plan.id.desc())
    if plan_date is not None:
        query = query.where(Plan.plan_date == plan_date)
    result = await session.execute(query)
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
