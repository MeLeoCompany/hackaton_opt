"""Синхронизация маршрутов с планом — отладка в режиме демонстрации.

Выбранные бригады приводятся к тому, что написано в плане на текущее системное время: что
по плану уже сделано — «Выполнена», где бригада должна работать сейчас — «В работе», куда
она сейчас едет — «В пути», остальное — «В плане». Отметки бригады (выехала, прибыла,
закончила) ставятся по плановым временам. Невыбранные бригады остаются как есть — так одних
можно «пустить по плану», а другие оставить отстающими и посмотреть, что сделает algoV2.

Время можно двигать в обе стороны, поэтому синхронизация ходит мимо таблицы переходов
(в том числе «Выполнена» → «В плане»): это отладочная правка, и она видна в истории заявки.
Отменённые и снятые с плана заявки не трогаем: отмена — решение, а не время.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.models import Assignment, Plan, RequestStatusId
from src.repositories.brigade import brigade_repository
from src.repositories.plans import plans_repository
from src.repositories.request_statuses import request_statuses_repository
from src.schemas.plans import PlanSyncReport
from src.services.planner import planning_service
from src.services.requests import request_status_service
from src.services.system import system_service

SYNC_COMMENT = "Синхронизация с планом (режим демонстрации)"


@dataclass(frozen=True)
class PlannedState:
    """Где бригада должна быть по плану на момент синхронизации."""

    status_id: int
    departed_at: datetime | None
    arrived_at: datetime | None
    finished_at: datetime | None


def planned_state(
    departed: datetime, start: datetime, duration_minutes: int, now: datetime
) -> PlannedState:
    """По плану бригада выезжает так, чтобы успеть к началу работ, начинает в плановое время
    и работает норматив. Отсюда статус и отметки на момент now."""
    end = start + timedelta(minutes=duration_minutes)
    if now >= end:
        return PlannedState(RequestStatusId.DONE, departed, start, end)
    if now >= start:
        return PlannedState(RequestStatusId.IN_PROGRESS, departed, start, None)
    if now >= departed:
        return PlannedState(RequestStatusId.EN_ROUTE, departed, None, None)
    return PlannedState(RequestStatusId.PLANNED, None, None, None)


def travel_by_request(detail) -> dict[int, float]:
    """Сколько минут бригада едет до каждой заявки маршрута — по плечам плана.

    У дорог одно плечо на заявку; у общественного транспорта плеч к заявке бывает несколько,
    и у каждого проставлен номер заявки в маршруте. Ожидание на остановке — тоже дорога.
    """
    minutes: dict[int, float] = {}
    for route in detail.routes:
        per_visit: dict[int, float] = {}
        numbered = any(leg.visit_index is not None for leg in route.legs)
        for position, leg in enumerate(route.legs):
            index = leg.visit_index if numbered else position
            if index is None:
                continue
            per_visit[index] = per_visit.get(index, 0.0) + leg.duration_min + leg.wait_min
        for index, visit in enumerate(route.visits):
            if index in per_visit:
                minutes[visit.request_id] = per_visit[index]
    return minutes


async def sync_routes(
    session: AsyncSession,
    plan: Plan,
    engineer_ids: list[int],
    *,
    user_id: int | None,
    travel_minutes: dict[int, float] | None = None,
) -> Counter:
    """Приводит маршруты выбранных бригад к плану; возвращает, сколько заявок в каком статусе."""
    now = clock.now()
    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    routes: dict[int, list[Assignment]] = {}
    for assignment in assignments:
        if assignment.engineer_id in engineer_ids and assignment.planned_arrival_time:
            routes.setdefault(assignment.engineer_id, []).append(assignment)

    statuses = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    counts: Counter = Counter()
    for route in routes.values():
        route.sort(key=lambda assignment: assignment.visit_order or 0)
        # бригада свободна с начала смены, дальше — с конца предыдущей работы по плану
        free_from = route[0].engineer.shift_start
        for assignment in route:
            request = assignment.request
            start = assignment.planned_arrival_time
            work_end = start + timedelta(minutes=request.duration_minutes)
            if request.approved_plan_id != plan.id or request.status_id == RequestStatusId.CANCELLED:
                free_from = work_end
                continue
            # выезжает, чтобы приехать к началу работ, но не раньше, чем освободилась
            travel = (travel_minutes or {}).get(request.id)
            departed = free_from if travel is None else max(free_from, start - timedelta(minutes=travel))
            state = planned_state(min(departed, start), start, request.duration_minutes, now)
            if request.status_id != state.status_id:
                request_statuses_repository.add_history(
                    session,
                    [request.id],
                    request.status_id,
                    state.status_id,
                    manual=True,
                    user_id=user_id,
                    plan_id=plan.id,
                    comment=SYNC_COMMENT,
                )
                request_status_service.set_status(request, statuses[state.status_id])
            fact = await brigade_repository.get_or_add_fact(
                session, request.id, assignment.engineer_id
            )
            fact.departed_at = state.departed_at
            fact.arrived_at = state.arrived_at
            fact.finished_at = state.finished_at
            fact.updated_at = now
            # бригада идёт по плану — прежнее разрешение выезда больше ни к чему
            request.departure_allowed_at = None
            counts[state.status_id] += 1
            free_from = work_end
    await session.flush()
    return counts


async def sync_plan(
    session: AsyncSession,
    plan_id: int,
    engineer_ids: list[int],
    *,
    office_id: int,
    user_id: int | None,
) -> PlanSyncReport:
    """Синхронизация из интерфейса: проверки, сама правка и обновлённый план."""
    await system_service.require_demo_mode(session)
    plan = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if plan.approved_at is None or plan.superseded_at is not None:
        raise planning_service.PlanInUseError(
            f"Синхронизировать можно только действующий утверждённый план, а план №{plan_id} — нет"
        )
    # время в пути до заявок — из маршрутов плана: по нему видно, когда бригада выезжает
    before = await planning_service.get_plan_detail(session, plan_id, office_id=office_id)
    counts = await sync_routes(
        session, plan, engineer_ids, user_id=user_id, travel_minutes=travel_by_request(before)
    )
    await session.commit()
    return PlanSyncReport(
        routes=len(set(engineer_ids)),
        done=counts[RequestStatusId.DONE],
        in_progress=counts[RequestStatusId.IN_PROGRESS],
        en_route=counts[RequestStatusId.EN_ROUTE],
        planned=counts[RequestStatusId.PLANNED],
        plan=await planning_service.get_plan_detail(session, plan_id, office_id=office_id),
    )
