"""Выдача оборудования бригадам по плану дня.

По первому плану видно, сколько штук нужно каждой бригаде на её заявки — это x0. Выдаём
`items = min(ёмкость транспорта, x0 + запас)`: запас (общая настройка системы) нужен на
брак и на заявки, которые появятся в течение дня, а ёмкость из справочника не даёт
выписать больше, чем бригада физически увезёт.

Рекомендацию диспетчер правит и утверждает — только тогда числа уходят в запас смен
(`engineer_equipment`). Дальше пересчёты считают от него: `replan_service` вычитает то,
что бригада уже израсходовала или везёт к заявке, зафиксированной на момент выезда T+15.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, NotFoundError
from src.models import Engineer, Equipment, Transport
from src.repositories.engineers import engineers_repository
from src.repositories.equipment import equipment_repository
from src.repositories.plans import plans_repository
from src.repositories.system import system_repository
from src.schemas.equipment import (
    IssueBrigade,
    IssueBrigadeWrite,
    IssueDone,
    IssueItem,
    IssuePreview,
)
from src.services.planner import planner_loader


class PlanNotFoundError(NotFoundError):
    """Плана нет или он из чужого офиса."""


class IssueDataError(DataError):
    """Выдача не прошла проверку: больше ёмкости или неизвестная бригада."""


async def preview(session: AsyncSession, plan_id: int, *, office_id: int) -> IssuePreview:
    """Что предложить выдать бригадам по этому плану."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None or plan.office_id != office_id:
        raise PlanNotFoundError(f"Плана №{plan_id} нет")

    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    # x0: сколько штук нужно бригаде на её заявки этого плана
    needed: dict[int, dict[int, int]] = {}
    counted: dict[int, int] = {}
    for assignment in assignments:
        counted[assignment.engineer_id] = counted.get(assignment.engineer_id, 0) + 1
        stock = needed.setdefault(assignment.engineer_id, {})
        for item in assignment.request.equipment:
            stock[item.equipment_id] = stock.get(item.equipment_id, 0) + item.quantity

    # бригады берём по смене дня, а не только тех, кому что-то досталось: пустой бригаде
    # тоже везти запас — на заявки, которые появятся днём
    day = planner_loader.planning_day(plan.plan_date)
    engineers = await engineers_repository.list_engineers_in_period(
        session, day.day_start, day.day_end, office_id=office_id
    )
    known = {engineer.id for engineer in engineers}
    extra = [
        engineer
        for engineer in await _engineers_by_ids(session, set(needed) - known)
        if engineer is not None
    ]
    engineers = sorted(engineers + extra, key=lambda engineer: engineer.input_order)

    reserve = (await system_repository.get_solver_settings(session)).equipment_reserve
    capacity = await equipment_repository.capacity_map(session)
    names = await _equipment_names(session)
    transports = await _transport_names(session)

    return IssuePreview(
        plan_id=plan.id,
        reserve=reserve,
        brigades=[
            IssueBrigade(
                engineer_id=engineer.id,
                name=engineer.name,
                transport_id=engineer.transport_id,
                transport_name=transports.get(engineer.transport_id, ""),
                requests=counted.get(engineer.id, 0),
                items=[
                    _item(
                        equipment_id=equipment_id,
                        name=name,
                        need=needed.get(engineer.id, {}).get(equipment_id, 0),
                        limit=capacity.get((engineer.transport_id, equipment_id), 0),
                        current=_current(engineer).get(equipment_id, 0),
                        reserve=reserve,
                    )
                    for equipment_id, name in names.items()
                ],
            )
            for engineer in engineers
        ],
    )


def _item(*, equipment_id: int, name: str, need: int, limit: int, current: int, reserve: int):
    return IssueItem(
        equipment_id=equipment_id,
        equipment_name=name,
        needed=need,
        capacity=limit,
        current=current,
        recommended=min(limit, need + reserve),
    )


async def apply(
    session: AsyncSession,
    plan_id: int,
    brigades: list[IssueBrigadeWrite],
    *,
    office_id: int,
) -> IssueDone:
    """Записать утверждённую выдачу в запас смен: дальше от него считают пересчёты."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None or plan.office_id != office_id:
        raise PlanNotFoundError(f"Плана №{plan_id} нет")

    capacity = await equipment_repository.capacity_map(session)
    names = await _equipment_names(session)
    problems: list[str] = []
    changed = 0
    total = 0
    for row in brigades:
        engineer = await session.get(Engineer, row.engineer_id)
        if engineer is None or engineer.office_id != office_id:
            problems.append(f"бригады №{row.engineer_id} нет")
            continue
        quantities: dict[int, int] = {}
        for item in row.items:
            limit = capacity.get((engineer.transport_id, item.equipment_id), 0)
            if item.quantity > limit:
                name = names.get(item.equipment_id, f"№{item.equipment_id}")
                problems.append(f"{engineer.name}: «{name}» — {item.quantity} шт, а увезёт {limit}")
                continue
            if item.quantity:
                quantities[item.equipment_id] = item.quantity
        engineers_repository.set_equipment(engineer, quantities)
        changed += 1
        total += sum(quantities.values())
    if problems:
        raise IssueDataError(problems)
    await session.commit()
    return IssueDone(brigades=changed, items=total)


def _current(engineer: Engineer) -> dict[int, int]:
    return {item.equipment_id: item.quantity for item in engineer.equipment_items}


async def _equipment_names(session: AsyncSession) -> dict[int, str]:
    rows = await session.execute(select(Equipment).order_by(Equipment.id))
    return {item.id: item.name for item in rows.scalars().all()}


async def _transport_names(session: AsyncSession) -> dict[int, str]:
    rows = await session.execute(select(Transport).order_by(Transport.id))
    return {item.id: item.name for item in rows.scalars().all()}


async def _engineers_by_ids(session: AsyncSession, ids: set[int]) -> list[Engineer | None]:
    """Бригады из плана, чья смена в день плана уже не числится — их всё равно показываем."""
    return [await session.get(Engineer, engineer_id) for engineer_id in sorted(ids)]
