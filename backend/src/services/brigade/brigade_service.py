"""Мобильное приложение бригады: маршрут дня и отметки по заявкам.

Бригада видит свой маршрут из утверждённого плана офиса и по ходу дня отмечает:
- «Выехали» — заявка «В пути», запоминается время выезда;
- «На месте» — заявка «В работе», время прибытия (если выезд не отметили — тоже «В работе»);
- «Выполнено» — заявка «Выполнена», время окончания;
- «Не выполнить» — заявка «Отменена» с причиной.
Статус меняется тем же переходом, что у оператора: действует таблица переходов и правило
разрывов (следующую заявку не начать, пока не закрыта прошлая). Каждая смена — в истории
заявки с именем учётки бригады, время отметок — в request_fact: по ним диспетчер видит факт
на карте плана, отставание от плана и пересчитывает остаток дня.
"""

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.errors import DataError, NotFoundError
from src.core.local_day import local_timezone
from src.models import AppUser, Assignment, Request, RequestStatusId
from src.repositories.brigade import brigade_repository
from src.repositories.plans import plans_repository
from src.repositories.references import references_repository
from src.repositories.request_statuses import request_statuses_repository
from src.repositories.requests import requests_repository
from src.schemas.brigade import BrigadeDays, BrigadeEquipment, BrigadeRoute, BrigadeVisit
from src.services.planner import departure_gate, planning_service
from src.services.planner.planner_problem import LOWEST_PRIORITY_LEVEL
from src.services.requests import request_status_service


class BrigadeActionError(DataError):
    """Отметку сделать нельзя: заявка не в маршруте бригады, уже закрыта или отмечена."""


class BrigadeVisitNotFoundError(NotFoundError):
    """Такой заявки в маршруте бригады нет."""


def now() -> datetime:
    """Системное время: для демонстрации его можно перемотать (core/clock.py)."""
    return clock.now()


async def route_days(session: AsyncSession, user: AppUser) -> BrigadeDays:
    """Дни с маршрутом; открываем сегодняшний, если его нет — ближайший будущий, иначе последний.

    Маршрутов нет вовсе (план ещё не утвердили) — открываем сегодня: в приложении всё равно
    видно, какой день показан.
    """
    days = await brigade_repository.list_route_days(session, user.office_id, user.brigade_id)
    today = now().astimezone(local_timezone()).date()
    if today in days:
        default_day = today
    else:
        default_day = next((day for day in days if day > today), days[-1] if days else today)
    return BrigadeDays(days=days, default_day=default_day)


async def route_assignments(session: AsyncSession, user: AppUser, plan_id: int) -> list[Assignment]:
    """Визиты бригады в плане по порядку."""
    assignments = [
        assignment
        for assignment in await plans_repository.list_plan_assignments(session, plan_id)
        if assignment.engineer is not None
        and assignment.engineer.brigade_id == user.brigade_id
        and assignment.planned_arrival_time is not None
    ]
    return sorted(assignments, key=lambda assignment: assignment.visit_order or 0)


async def get_route(session: AsyncSession, user: AppUser, plan_date: date) -> BrigadeRoute:
    plan = await plans_repository.get_approved_plan(session, plan_date, office_id=user.office_id)
    # учётка бригады называется её именем (справочник бригад держит их одинаковыми)
    route = BrigadeRoute(plan_date=plan_date, brigade_name=user.name)
    if plan is None:
        return route
    assignments = await route_assignments(session, user, plan.id)
    route.plan_id = plan.id
    if not assignments:
        return route

    statuses = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    work_types = {
        item.id: item.name for item in await references_repository.list_work_types(session)
    }
    priorities = {item.id: item for item in await references_repository.list_priorities(session)}
    equipment = {item.id: item.name for item in await references_repository.list_equipment(session)}
    facts = await brigade_repository.list_facts(
        session, [assignment.request_id for assignment in assignments]
    )
    cancels = await request_statuses_repository.cancellations(
        session, [assignment.request_id for assignment in assignments]
    )

    engineer = assignments[0].engineer
    route.shift_start, route.shift_end = engineer.shift_start, engineer.shift_end
    route.start_latitude = float(engineer.start_latitude)
    route.start_longitude = float(engineer.start_longitude)
    for assignment in assignments:
        request = assignment.request
        status = statuses[request.status_id]
        fact = facts.get(request.id)
        priority = priorities.get(request.priority_id)
        route.visits.append(
            BrigadeVisit(
                request_id=request.id,
                visit_order=assignment.visit_order or 0,
                address=request.address,
                latitude=float(request.latitude),
                longitude=float(request.longitude),
                window_start=request.window_start,
                window_end=request.window_end,
                planned_arrival_time=assignment.planned_arrival_time,
                duration_minutes=request.duration_minutes,
                work_type=work_types.get(request.work_type_id),
                priority=priority.name if priority else "",
                priority_level=priority.level if priority else LOWEST_PRIORITY_LEVEL,
                equipment=[
                    BrigadeEquipment(
                        name=equipment.get(item.equipment_id, "—"), quantity=item.quantity
                    )
                    for item in request.equipment
                ],
                status_id=status.id,
                status_code=status.code,
                status_name=status.name,
                removed=request.approved_plan_id != plan.id,
                departed_at=fact.departed_at if fact else None,
                arrived_at=fact.arrived_at if fact else None,
                finished_at=fact.finished_at if fact else None,
                cancel_reason=request.cancel_reason,
                cancelled_at=cancels[request.id][0].changed_at if request.id in cancels else None,
                cancelled_by=cancelled_by(cancels.get(request.id)),
            )
        )
    await apply_departure_gate(session, plan, route, assignments)
    return route


# кто отменил заявку — словами для карточки визита (docs/algoV2.md, шаг 11)
CANCELLED_BY = {"brigade": "бригадой", "dispatcher": "диспетчером", "admin": "диспетчером"}


def cancelled_by(cancellation) -> str | None:
    if cancellation is None:
        return None
    _, role = cancellation
    return CANCELLED_BY.get(role, "системой")


async def apply_departure_gate(
    session: AsyncSession,
    plan,
    route: BrigadeRoute,
    assignments: list[Assignment],
) -> None:
    """Закрыть выезд, если бригада выбилась из плана или идёт пересчёт (docs/algoV2.md).

    Проверяем только ближайшую незакрытую заявку: остальные и так впереди.
    """
    next_visit = next(
        (visit for visit in route.visits if visit.status_code in ("planned", "new")), None
    )
    if next_visit is None:
        return
    assignment = next(item for item in assignments if item.request_id == next_visit.request_id)
    check = await departure_state(
        session, plan, assignment.request, assignment, assignments, next_visit.departed_at
    )
    next_visit.can_depart = check.allowed
    next_visit.blocked_reason = check.reason


async def departure_state(
    session: AsyncSession,
    plan,
    request: Request,
    assignment: Assignment,
    assignments: list[Assignment],
    departed_at: datetime | None,
) -> departure_gate.DepartureCheck:
    """Можно ли выезжать на эту заявку: общее правило для приложения и для отметки."""
    delays = await planning_service.plan_route_delays(session, plan, assignments)
    at_risk = any(request.id in delay.at_risk_request_ids for delay in delays.values())
    return departure_gate.check_departure(
        planned_start=assignment.planned_arrival_time,
        departed_at=departed_at,
        at_risk=at_risk,
        allowed_at=request.departure_allowed_at,
        replan_sends_elsewhere=planning_service.sends_elsewhere(
            await planning_service.replan_next_visits(session, plan.id),
            assignment.engineer_id,
            request.id,
        ),
        now=now(),
    )


async def require_departure_allowed(
    session: AsyncSession, user: AppUser, request: Request, assignment: Assignment
) -> None:
    """Выехать нельзя, пока бригада выбилась из плана: ждёт нового или разрешения оператора."""
    plan = await plans_repository.get_plan(session, assignment.plan_id)
    assignments = await route_assignments(session, user, plan.id)
    check = await departure_state(session, plan, request, assignment, assignments, None)
    if not check.allowed:
        raise BrigadeActionError([check.reason or "выезд пока закрыт"])


async def find_route_visit(
    session: AsyncSession, user: AppUser, request_id: int
) -> tuple[Request, Assignment]:
    """Заявка из маршрута этой бригады в утверждённом плане — иначе отмечать нечего."""
    request = await requests_repository.get_request(session, request_id)
    if request is None or request.office_id != user.office_id:
        raise BrigadeVisitNotFoundError(f"Заявка №{request_id} не найдена")
    if request.approved_plan_id is None:
        raise BrigadeActionError([f"заявку №{request_id} сняли с плана — ехать к ней не нужно"])
    for assignment in await route_assignments(session, user, request.approved_plan_id):
        if assignment.request_id == request_id:
            return request, assignment
    raise BrigadeActionError([f"заявки №{request_id} нет в маршруте бригады «{user.name}»"])


async def mark(
    session: AsyncSession, user: AppUser, request_id: int, action: str, reason: str = ""
) -> BrigadeRoute:
    """Отметка бригады по заявке; возвращает обновлённый маршрут дня."""
    request, assignment = await find_route_visit(session, user, request_id)
    if request.status_id in (RequestStatusId.DONE, RequestStatusId.CANCELLED):
        raise BrigadeActionError(
            [f"заявка №{request_id} уже «{request.status.name}» — отмечать по ней нечего"]
        )
    fact = await brigade_repository.get_or_add_fact(session, request_id, assignment.engineer_id)
    moment = now()

    async def to_status(status_id: int, comment: str) -> None:
        await request_status_service.change_status(
            session, [request], status_id, manual=True, user_id=user.id, comment=comment
        )

    if action == "depart":
        if fact.departed_at is not None:
            raise BrigadeActionError([f"выезд на заявку №{request_id} уже отмечен"])
        await require_departure_allowed(session, user, request, assignment)
        await to_status(RequestStatusId.EN_ROUTE, "Бригада выехала")
        fact.departed_at = moment
    elif action == "arrive":
        if fact.arrived_at is not None:
            raise BrigadeActionError([f"прибытие на заявку №{request_id} уже отмечено"])
        # выезд забыли отметить — прибытие его подразумевает
        await to_status(RequestStatusId.IN_PROGRESS, "Бригада на месте")
        fact.departed_at = fact.departed_at or moment
        fact.arrived_at = moment
    elif action == "done":
        await to_status(RequestStatusId.DONE, "Бригада: выполнено")
        fact.finished_at = moment
    elif action == "fail":
        await to_status(RequestStatusId.CANCELLED, f"Бригада: не выполнено — {reason}")
        fact.finished_at = moment
    else:
        raise BrigadeActionError([f"неизвестная отметка «{action}»"])
    fact.updated_at = moment

    plan = await plans_repository.get_plan(session, assignment.plan_id)
    await session.commit()
    return await get_route(session, user, plan.plan_date)
