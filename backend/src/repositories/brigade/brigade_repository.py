"""Маршрут бригады и её отметки по заявкам. Коммит делает сервис — здесь только запросы."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Assignment, Engineer, Plan, RequestFact


async def list_route_days(session: AsyncSession, office_id: int, brigade_id: int) -> list[date]:
    """Дни, на которые у бригады есть маршрут в утверждённом плане офиса."""
    result = await session.execute(
        select(Plan.plan_date)
        .join(Assignment, Assignment.plan_id == Plan.id)
        .join(Engineer, Engineer.id == Assignment.engineer_id)
        .where(
            Plan.office_id == office_id,
            Plan.approved_at.is_not(None),
            Plan.superseded_at.is_(None),
            Plan.plan_date.is_not(None),
            Engineer.brigade_id == brigade_id,
        )
        .distinct()
        .order_by(Plan.plan_date)
    )
    return list(result.scalars().all())


async def list_facts(session: AsyncSession, request_ids: list[int]) -> dict[int, RequestFact]:
    if not request_ids:
        return {}
    result = await session.execute(
        select(RequestFact).where(RequestFact.request_id.in_(request_ids))
    )
    return {fact.request_id: fact for fact in result.scalars().all()}


async def get_or_add_fact(session: AsyncSession, request_id: int, engineer_id: int) -> RequestFact:
    fact = await session.get(RequestFact, request_id)
    if fact is None:
        fact = RequestFact(request_id=request_id, engineer_id=engineer_id)
        session.add(fact)
    return fact
