"""Пересчёт утверждённого плана с текущего момента.

Бригады уже работают по утверждённому плану и отмечают в мобильном приложении выезд, прибытие
и выполнение. Если кто-то выбился из графика, появились новые заявки или часть сняли,
диспетчер пересчитывает остаток дня:

- выполненные, отменённые и начатые («В пути», «В работе») заявки остаются за бригадами — в новом
  плане они первыми в маршруте с прежним временем, решатель их не двигает;
- бригада стартует оттуда, где она сейчас: с заявки, на которой работает (свободна, когда
  закончит), или с последней закрытой; если ещё не выезжала — с утреннего старта, но не
  раньше момента пересчёта;
- остальное — не начатые заявки «В плане» и «Новые» заявки дня — решатель раскладывает
  заново, со своими окнами. Куда уже не успеть, остаётся неназначенным с причиной.

Пересчёт — отдельный план (run_type replanned) со ссылкой на пересчитанный. Утверждение
пересчёта (planning_service.approve_plan) заменяет пересчитанный план.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.config import settings
from src.core.errors import ExternalServiceError
from src.core.local_day import local_timezone
from src.models import Assignment, Plan, PlanRunType, RequestStatusId
from src.repositories.brigade import brigade_repository
from src.repositories.plans import plans_repository
from src.repositories.request_statuses import request_statuses_repository
from src.repositories.requests import requests_repository
from src.schemas.plans import (
    BrigadeFreeAt,
    PlanSummary,
    ReplanDecision,
    ReplanPreview,
    ReplanProblem,
    SolverName,
)
from src.schemas.travel import Point, TransportKind, TravelProvider
from src.services.planner import planner_loader, planning_service, window_suggestions
from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    validate_objective_order,
)
from src.services.planner.planner_loader import EngineerStart
from src.services.planner.planning_service import PlanDataError, PlanDistance, PlanInUseError
from src.services.requests import request_status_service
from src.services.travel import build_route

# заявки, которые бригада уже закрыла или начала: в пересчёте они остаются на месте
KEPT_STATUSES = (
    RequestStatusId.DONE,
    RequestStatusId.CANCELLED,
    RequestStatusId.EN_ROUTE,
    RequestStatusId.IN_PROGRESS,
)
# бригада занялась заявкой: едет к ней или работает на месте
STARTED_STATUSES = (RequestStatusId.EN_ROUTE, RequestStatusId.IN_PROGRESS)


async def replan(
    session: AsyncSession,
    plan_id: int,
    solver: SolverName = SolverName.CUOPT,
    objective_order: list[ObjectiveCriterion]
    | tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    at: datetime | None = None,
    *,
    office_id: int,
    decisions: list[ReplanDecision] | None = None,
    free_at: list[BrigadeFreeAt] | None = None,
    user_id: int | None = None,
) -> PlanSummary:
    """Пересчитывает утверждённый план с момента at (по умолчанию — сейчас).

    decisions — что диспетчер решил по заявкам, на которые не успеваем (пробный пересчёт):
    новое окно или отмена. Применяются в той же транзакции до расчёта: если расчёт не
    получился, не меняется ничего.
    """
    parent, at = await replannable(session, plan_id, at, office_id=office_id)
    await apply_decisions(session, parent, decisions or [], office_id=office_id, user_id=user_id)
    built = await build_replan(
        session, parent, solver, objective_order, at, office_id=office_id, free_at=free_at
    )
    plan = built.plan
    planning_service.set_plan_distance(plan, await full_routes_distance(session, plan))
    await session.commit()
    return (await planning_service.summarize_plans(session, [plan]))[0]


async def preview_replan(
    session: AsyncSession,
    plan_id: int,
    solver: SolverName = SolverName.CUOPT,
    objective_order: list[ObjectiveCriterion]
    | tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    at: datetime | None = None,
    *,
    office_id: int,
    free_at: list[BrigadeFreeAt] | None = None,
) -> ReplanPreview:
    """Пробный пересчёт: тот же расчёт, но ничего не сохраняется.

    По заявкам, которые никто не успевает, сразу считается второй расчёт с раскрытыми окнами
    (docs/algoV2.md, шаги 2-3): он даёт конкретное время, которое оператор называет клиенту.
    """
    parent, at = await replannable(session, plan_id, at, office_id=office_id)
    try:
        built = await build_replan(
            session, parent, solver, objective_order, at, office_id=office_id, free_at=free_at
        )
        assignments = await plans_repository.list_plan_assignments(session, built.plan.id)
        unassigned = [a for a in assignments if a.engineer_id is None]
        suggestions = await window_suggestions.suggest_windows(
            built.loaded,
            solver,
            validate_objective_order(objective_order),
            {a.request_id for a in unassigned},
        )
        tolerance = timedelta(minutes=settings.promise_tolerance_minutes)
        preview = ReplanPreview(
            assigned_count=sum(1 for a in assignments if a.engineer_id is not None),
            promise_tolerance_minutes=settings.promise_tolerance_minutes,
            unassigned=[
                ReplanProblem(
                    request_id=a.request_id,
                    address=a.request.address,
                    window_start=a.request.window_start,
                    window_end=a.request.window_end,
                    status_id=a.request.status_id,
                    reason=a.unassigned_reason or "",
                    expired=a.request.window_end < at,
                    suggested_start=suggestion.start if suggestion else None,
                    suggested_end=suggestion.start + tolerance if suggestion else None,
                    suggested_engineer=suggestion.engineer_name if suggestion else None,
                )
                for a in unassigned
                if (suggestion := suggestions.get(a.request_id)) or True
            ],
        )
    finally:
        await session.rollback()
    return preview


async def replannable(
    session: AsyncSession, plan_id: int, at: datetime | None, *, office_id: int
) -> tuple[Plan, datetime]:
    """Действующий утверждённый план и момент пересчёта в пределах его дня."""
    parent = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if parent.approved_at is None or parent.superseded_at is not None or parent.plan_date is None:
        raise PlanInUseError(
            f"Пересчитать можно только действующий утверждённый план, а план №{plan_id} — нет"
        )
    at = at or clock.now()
    day = planner_loader.planning_day(parent.plan_date)
    if at >= day.day_end:
        raise PlanDataError(
            [
                f"день {parent.plan_date:%d.%m.%Y} уже закончился — пересчитывать нечего. "
                "Для демонстрации переведите системные часы во вкладке «Система»"
            ]
        )
    return parent, max(at, day.day_start)


@dataclass
class ReplanResult:
    """Посчитанный пересчёт: сам план и задача, из которой он получился."""

    plan: Plan
    loaded: planner_loader.LoadedDay
    solution: object


async def build_replan(
    session: AsyncSession,
    parent: Plan,
    solver: SolverName,
    objective_order: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
    at: datetime,
    *,
    office_id: int,
    free_at: list[BrigadeFreeAt] | None = None,
) -> ReplanResult:
    """Считает пересчёт и записывает его в сессию (без коммита).

    free_at — когда бригада освободится со слов оператора (docs/algoV2.md, шаг 10).
    """
    day = planner_loader.planning_day(parent.plan_date)
    assignments = await plans_repository.list_plan_assignments(session, parent.id)
    told = {item.engineer_id: item.free_at for item in free_at or []}
    fixed, starts = await brigade_positions(session, parent, assignments, at, told)

    loaded = await planner_loader.load_day(session, day, office_id, starts=starts, not_before=at)
    # раскладывать может быть нечего: всё закрыто, начато или перенесено решениями оператора.
    # Это не ошибка — пересчёт выйдет из одних закреплённых визитов, иначе решения откатятся
    if loaded.instance.n_engineers == 0:
        raise PlanDataError(["на этот момент ни у одной бригады не осталось смены"])

    policy = validate_objective_order(objective_order)
    started = time.perf_counter()
    solution = await planning_service.solve_with(solver, loaded, policy)
    duration_ms = (time.perf_counter() - started) * 1000

    plan = await planning_service.save_solution(
        session,
        loaded,
        solution,
        run_type=PlanRunType.REPLANNED,
        solver=solver.value,
        solve_duration_ms=duration_ms,
        objective_order=policy if solver is SolverName.CUOPT else None,
        fixed=fixed,
    )
    plan.parent_plan_id = parent.id
    plan.replanned_at = at
    await session.flush()
    return ReplanResult(plan=plan, loaded=loaded, solution=solution)


async def apply_decisions(
    session: AsyncSession,
    parent: Plan,
    decisions: list[ReplanDecision],
    *,
    office_id: int,
    user_id: int | None,
) -> None:
    """Решения оператора по заявкам, на которые не успеваем (docs/algoV2.md, шаг 4).

    agree — клиент согласен на предложенное время: окно сужается до обещанного, ставится
    отметка «согласовано»; move — не может сегодня: окно уезжает на другой день, отметка
    «перенесена»; cancel и no_answer — отмена с причиной, у no_answer ещё «требует уточнения».
    Решать можно только о заявках, которые пересчёт раскладывает: «Новых» без плана и не
    начатых «В плане» этого плана. Новое окно снимает заявку с плана.
    """
    if not decisions:
        return
    await request_status_service.require_transition(
        session, RequestStatusId.PLANNED, RequestStatusId.NEW, manual=False
    )
    statuses = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    problems = []
    requests = {}
    for decision in decisions:
        request = await requests_repository.get_request(session, decision.request_id)
        if request is None or request.office_id != office_id:
            problems.append(f"заявка №{decision.request_id} не найдена")
            continue
        new = request.status_id == RequestStatusId.NEW and request.approved_plan_id is None
        planned = (
            request.status_id == RequestStatusId.PLANNED and request.approved_plan_id == parent.id
        )
        if not (new or planned):
            problems.append(
                f"заявка №{request.id} уже «{request.status.name}» — решать по ней нечего, "
                "проверьте пересчёт ещё раз"
            )
        requests[decision.request_id] = request
    if problems:
        raise PlanDataError(problems)

    for decision in decisions:
        request = requests[decision.request_id]
        if decision.action in ("cancel", "no_answer"):
            no_answer = decision.action == "no_answer"
            reason = decision.reason.strip() or (
                "не дозвонились" if no_answer else "клиент отказался"
            )
            request.cancel_reason = reason
            request.needs_followup = no_answer
            await request_status_service.change_status(
                session,
                [request],
                RequestStatusId.CANCELLED,
                manual=True,
                user_id=user_id,
                comment=f"Отменена при пересчёте плана №{parent.id}: {reason}",
            )
            continue

        window = f"{local_text(decision.window_start)}–{local_text(decision.window_end)}"
        agreed = decision.action == "agree"
        comment = (
            f"Согласовано с клиентом: {window}"
            if agreed
            else f"Перенесена по договорённости на {window}"
        )
        detach_from_plan(session, request, parent, statuses, user_id, comment)
        request.window_start = decision.window_start
        request.window_end = decision.window_end
        if agreed:
            # обещание клиенту: заявка держится в этом окне и защищена ярусом в расчёте
            request.promised_from = decision.window_start
            request.promised_to = decision.window_end
        else:
            # на другой день узкое окно не тащим, зато помним, что работу уже двигали
            request.promised_from = request.promised_to = None
            request.moved_from = parent.plan_date
    await session.flush()


def detach_from_plan(
    session: AsyncSession,
    request,
    parent: Plan,
    statuses: dict,
    user_id: int | None,
    comment: str,
) -> None:
    """Снять заявку с утверждённого плана: окно можно менять только у «Новой»."""
    if request.status_id != RequestStatusId.PLANNED:
        return
    request_statuses_repository.add_history(
        session,
        [request.id],
        RequestStatusId.PLANNED,
        RequestStatusId.NEW,
        manual=False,
        user_id=user_id,
        plan_id=parent.id,
        comment=comment,
    )
    request_status_service.set_status(request, statuses[RequestStatusId.NEW])
    request.approved_plan_id = None


def local_text(moment: datetime) -> str:
    return moment.astimezone(local_timezone()).strftime("%d.%m %H:%M")


async def brigade_positions(
    session: AsyncSession,
    parent: Plan,
    assignments: list[Assignment],
    at: datetime,
    free_at_by_engineer: dict[int, datetime] | None = None,
) -> tuple[dict[int, list[Assignment]], dict[int, EngineerStart]]:
    """Что каждая бригада уже закрыла или начала (остаётся за ней) и откуда она продолжает.

    free_at_by_engineer — когда бригада освободится со слов оператора: для застрявшей это
    честнее норматива (docs/algoV2.md, шаг 10).
    """
    facts = await brigade_repository.list_facts(
        session, [assignment.request_id for assignment in assignments]
    )
    routes: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        if assignment.engineer is not None and assignment.planned_arrival_time is not None:
            routes[assignment.engineer_id].append(assignment)

    fixed: dict[int, list[Assignment]] = {}
    starts: dict[int, EngineerStart] = {}
    for engineer_id, route in routes.items():
        route.sort(key=lambda assignment: assignment.visit_order or 0)
        kept = [
            assignment
            for assignment in route
            if assignment.request.approved_plan_id == parent.id
            and assignment.request.status_id in KEPT_STATUSES
        ]
        if kept:
            fixed[engineer_id] = kept

        engineer = route[0].engineer
        in_progress = next((a for a in kept if a.request.status_id in STARTED_STATUSES), None)
        done = [a for a in kept if a.request.status_id == RequestStatusId.DONE]
        if in_progress is not None:
            # работает на заявке или едет к ней: свободна, когда закончит
            request = in_progress.request
            fact = facts.get(request.id)
            work_start = (
                fact.arrived_at
                if fact and fact.arrived_at
                else max(at, in_progress.planned_arrival_time)
            )
            free_at = work_start + timedelta(minutes=request.duration_minutes)
            point = (float(request.latitude), float(request.longitude))
        elif done:
            # стоит на последней выполненной
            last = done[-1]
            fact = facts.get(last.request_id)
            free_at = (
                fact.finished_at
                if fact and fact.finished_at
                else last.planned_arrival_time + timedelta(minutes=last.request.duration_minutes)
            )
            point = (float(last.request.latitude), float(last.request.longitude))
        else:
            # ещё не выезжала — с утреннего старта
            free_at = engineer.shift_start
            point = (float(engineer.start_latitude), float(engineer.start_longitude))
        told = (free_at_by_engineer or {}).get(engineer_id)
        starts[engineer_id] = EngineerStart(
            latitude=point[0],
            longitude=point[1],
            available_from=max(at, told or free_at),
        )
    return fixed, starts


async def full_routes_distance(session: AsyncSession, plan: Plan) -> PlanDistance:
    """Пробег нового плана целиком: от утреннего старта через закрытые, начатые и новые визиты."""
    await session.flush()
    routes: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in await plans_repository.list_plan_assignments(session, plan.id):
        if assignment.engineer is not None and assignment.visit_order is not None:
            routes[assignment.engineer_id].append(assignment)

    async def route_distance(route: list[Assignment]) -> tuple[float, str]:
        route.sort(key=lambda assignment: assignment.visit_order)
        engineer = route[0].engineer
        points = [
            Point(
                latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude)
            )
        ]
        points += [
            Point(latitude=float(a.request.latitude), longitude=float(a.request.longitude))
            for a in route
        ]
        transport = TransportKind(engineer.transport_id)
        if transport is TransportKind.PUBLIC_TRANSPORT:
            departures = [engineer.shift_start]
            departures += [
                assignment.planned_arrival_time
                + timedelta(minutes=assignment.request.duration_minutes)
                for assignment in route[:-1]
            ]
            try:
                travel = await build_route(
                    points, transport, leg_departure_times=departures, allow_fallback=False
                )
            except (httpx.HTTPError, KeyError, ValueError) as error:
                raise ExternalServiceError(f"R5 не смог измерить пробег плана: {error}") from error
        else:
            travel = await build_route(points, transport)
        provider = (
            travel.provider.value
            if isinstance(travel.provider, TravelProvider)
            else str(travel.provider)
        )
        return travel.distance_km, provider

    distances = await asyncio.gather(*(route_distance(route) for route in routes.values()))
    providers = {provider for _, provider in distances}
    provider = providers.pop() if len(providers) == 1 else "mixed" if providers else None
    return PlanDistance(
        distance_km=round(sum(distance for distance, _ in distances), 3), provider=provider
    )
