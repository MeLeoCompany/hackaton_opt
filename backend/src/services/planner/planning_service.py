"""Построение плана дня выбранным решателем, сохранение и просмотр планов."""

import asyncio
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.config import settings
from src.core.errors import DataError, ExternalServiceError, InUseError, NotFoundError
from src.core.local_day import intersected_local_dates, local_timezone
from src.models import Assignment, Engineer, Plan, PlanRunType, Request, RequestStatusId
from src.repositories.brigade import brigade_repository
from src.repositories.brigades import brigades_repository
from src.repositories.plans import plans_repository
from src.repositories.references import references_repository
from src.repositories.request_statuses import request_statuses_repository
from src.repositories.requests import requests_repository
from src.schemas.plans import (
    BrokenPromise,
    EngineerRoute,
    HeldRequest,
    PlanDayCheck,
    PlanDetail,
    PlanningDayOption,
    PlanSummary,
    PlanVisit,
    SolverName,
    UnassignedRequest,
    WithdrawnRequest,
)
from src.schemas.system import SolverParams
from src.schemas.travel import Point, TransportKind, TravelProvider, TravelRoute
from src.services.planner import (
    baseline_solver,
    cuopt_solver,
    day_state,
    departure_gate,
    ortools_solver,
    planner_loader,
    run_log,
    transit_schedule,
)
from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    validate_objective_order,
)
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import TOP_PRIORITY_LEVEL
from src.services.planner.route_delay import RouteDelay, VisitFact, route_delay, visit_state
from src.services.requests import request_status_service
from src.services.travel import build_route, travel_cache

SOLVER_NAME = "cuopt"
# как шаг называется в журнале расчёта
SOLVER_STEPS = {
    SolverName.CUOPT: "Решаю задачу маршрутизации (cuOpt)",
    SolverName.ORTOOLS: "Решаю задачу маршрутизации (OR-Tools)",
    SolverName.BASELINE: "Базовый расчёт: первый подходящий исполнитель",
}

RUN_TYPE_BY_SOLVER = {
    SolverName.CUOPT: PlanRunType.OPTIMIZED,
    SolverName.ORTOOLS: PlanRunType.ORTOOLS,
    SolverName.BASELINE: PlanRunType.BASELINE,
}
AssignmentView = Assignment | SimpleNamespace

SCHEDULE_REASON = (
    "Подходящий исполнитель может выполнить заявку отдельно, но она не поместилась "
    "в общий план с учётом срочности, других заявок, времени дороги и смен"
)
TIME_REASON = (
    "Подходящие исполнители есть, но ни один не успевает приехать от начала смены, "
    "начать работу в окне заявки и закончить её до конца смены"
)
# бригада уже занялась заявкой: выехала, работает или закрыла её
WORKED_STATUSES = (
    RequestStatusId.EN_ROUTE,
    RequestStatusId.IN_PROGRESS,
    RequestStatusId.DONE,
)


class PlanNotFoundError(NotFoundError):
    """Плана с таким номером нет."""


class PlanInUseError(InUseError):
    """Действие с планом сейчас запрещено: сначала нужно снять утверждение."""


class PlanDataError(DataError):
    """План на этот день построить нельзя."""


async def list_planning_days(session: AsyncSession, *, office_id: int) -> list[PlanningDayOption]:
    """Московские дни, с которыми пересекаются окна активных заявок офиса."""
    requests = await requests_repository.list_active_requests(session, office_id=office_id)
    request_count_by_day: dict[date, int] = defaultdict(int)
    # просроченные: «Новая», а окно уже закрылось — хвост прошедшего дня. Пересчитать тот день
    # уже нельзя, поэтому такие заявки показываем отдельно: перенести или отменить
    overdue_by_day: dict[date, int] = defaultdict(int)
    now = clock.now()
    for request in requests:
        overdue = request.status_id == RequestStatusId.NEW and request.window_end <= now
        for plan_date in intersected_local_dates(request.window_start, request.window_end):
            request_count_by_day[plan_date] += 1
            if overdue:
                overdue_by_day[plan_date] += 1
    return [
        PlanningDayOption(
            plan_date=plan_date, active_requests=count, overdue_requests=overdue_by_day[plan_date]
        )
        for plan_date, count in sorted(request_count_by_day.items())
    ]


async def load_planning_day(session: AsyncSession, plan_date: date, office_id: int) -> LoadedDay:
    """Загружает данные дня офиса и проверяет наличие заявок и исполнителей."""
    day = planner_loader.planning_day(plan_date)
    loaded = await planner_loader.load_day(session, day, office_id)
    if loaded.instance.n_requests == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет активных заявок"])
    if loaded.instance.n_engineers == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет исполнителей со сменой"])

    return loaded


async def build_plan_for_day(
    session: AsyncSession,
    plan_date: date,
    solver: SolverName = SolverName.CUOPT,
    objective_order: list[ObjectiveCriterion]
    | tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    *,
    office_id: int,
    run_id: UUID | None = None,
    user_id: int | None = None,
    params: SolverParams | None = None,
) -> PlanSummary:
    """Считает план дня выбранным решателем и сохраняет его отдельной записью.

    Каждый расчёт — самостоятельный план со своими параметрами и метриками (время решателя,
    пробег, сколько заявок назначено). Пары для сравнения не создаются: сравнить можно любые
    два уже посчитанных плана.
    """
    async with run_log.track(
        "build",
        office_id=office_id,
        plan_date=plan_date,
        solver=solver.value,
        user_id=user_id,
        run_id=run_id,
    ):
        plan = await build_inside_run(
            session, plan_date, solver, objective_order, office_id=office_id, params=params
        )
        await session.commit()
        await run_log.attach_plan(plan.id)
        return (await summarize_plans(session, [plan]))[0]


async def build_inside_run(
    session: AsyncSession,
    plan_date: date,
    solver: SolverName,
    objective_order: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
    *,
    office_id: int,
    params: SolverParams | None = None,
) -> Plan:
    """Сам расчёт дня внутри запуска журнала: план записан в сессию, коммит — за вызывающим.

    Так перед расчётом в той же транзакции можно применить решения оператора по заявкам:
    не получился расчёт — не меняется ничего.
    """
    # параметры расчёта приходят из запроса; системные подставляет слой API
    params = params or SolverParams()
    loaded = await load_planning_day(session, plan_date, office_id)
    policy = validate_objective_order(objective_order)

    started = time.perf_counter()
    solution = await solve_with(solver, loaded, policy, params=params)
    duration_ms = (time.perf_counter() - started) * 1000

    async with run_log.step("Сохраняю план", 80, 92):
        plan = await save_solution(
            session,
            loaded,
            solution,
            run_type=RUN_TYPE_BY_SOLVER[solver],
            solver=solver.value,
            solve_duration_ms=duration_ms,
            objective_order=policy if solver is not SolverName.BASELINE else None,
        )
    # маршруты строятся один раз здесь и ложатся в кеш: открытие плана возьмёт готовые
    async with run_log.step("Строю маршруты бригад и считаю пробег", 92, 99):
        routes, _ = await plan_routes(session, plan, strict=True)
        set_plan_distance(plan, routes_distance(routes))
    return plan


async def solve_with(
    solver: SolverName,
    loaded: LoadedDay,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    ranks: dict[int, int] | None = None,
    params: SolverParams | None = None,
) -> cuopt_solver.DaySolution:
    """cuOpt считает на видеокарте, OR-Tools — на процессоре, базовый алгоритм — прямо здесь.

    ranks — ярусы заявок для целевой функции; нужны второму расчёту при синхронизации
    (docs/algoV2.md). Базовый алгоритм ярусы не использует.
    """
    async with run_log.step(SOLVER_STEPS[solver], 45, 80):
        if solver is SolverName.BASELINE:
            return baseline_solver.solve_day(loaded.instance)
        # у обоих решателей один вход и один выход, поэтому проверка расписания общая
        solve = (
            ortools_solver.solve_day
            if solver is SolverName.ORTOOLS
            else cuopt_solver.solve_day
        )
        return await transit_schedule.solve_day(
            loaded, objective_order, ranks, params, solve=solve
        )


@dataclass(frozen=True)
class PlanDistance:
    distance_km: float
    provider: str | None


def set_plan_distance(plan: Plan, distance: PlanDistance) -> None:
    plan.total_distance_km = Decimal(str(distance.distance_km))
    plan.distance_provider = distance.provider


async def delete_plan(session: AsyncSession, plan_id: int, *, office_id: int) -> None:
    """Удаляет план вместе с его назначениями — чтобы день можно было пересчитать заново."""
    plan = await find_plan(session, plan_id, office_id=office_id)
    if plan.approved_at is not None:
        raise PlanInUseError(
            f"План №{plan_id} утверждён: сначала снимите утверждение, иначе заявки останутся "
            "закреплёнными за несуществующим планом. По плану, который бригады уже видят, "
            "утверждение не снимают — он остаётся в истории дня"
        )
    await plans_repository.delete_plan(session, plan)
    await session.commit()


async def find_plan(session: AsyncSession, plan_id: int, *, office_id: int) -> Plan:
    """План офиса. Чужой выглядит как несуществующий."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None or plan.office_id != office_id:
        raise PlanNotFoundError(f"План №{plan_id} не найден")
    return plan


async def approve_plan(
    session: AsyncSession, plan_id: int, *, office_id: int, user_id: int | None = None
) -> PlanSummary:
    """Утверждает план дня и закрепляет за ним назначенные заявки.

    Заявка с окном через полночь попадает в оба дня, и планы обоих дней вправе её взять.
    Утверждение фиксирует, чей это день: закреплённую заявку другие дни больше не берут.
    """
    plan = await find_plan(session, plan_id, office_id=office_id)
    if plan.approved_at is not None:
        return (await summarize_plans(session, [plan]))[0]
    if getattr(plan, "parent_plan_id", None) is not None:
        return await approve_replan(session, plan, user_id=user_id)
    if plan.plan_date is None:
        raise PlanDataError(
            [f"План №{plan_id} создан до поддержки дней планирования и не может быть утверждён"]
        )
    plan_date = plan.plan_date

    approved = await plans_repository.get_approved_plan(session, plan_date, office_id=office_id)
    if approved is not None:
        raise PlanInUseError(
            f"На {plan_date:%d.%m.%Y} уже утверждён план №{approved.id}. Пока по нему "
            "не работают, утверждение можно снять; если работают — пересчитайте его, "
            "и утверждённый пересчёт его заменит"
        )

    # невлезшие заявки без решения не оставляем: иначе они молча висят «Новыми», пока окно
    # не закроется. Оператор переносит их, согласует время или отменяет (подбор окон при
    # утверждении) — перенесённая войдёт в план своего дня
    waiting = await waiting_unassigned(session, plan)
    if waiting:
        numbers = ", ".join(f"№{assignment.request_id}" for assignment in waiting)
        raise PlanInUseError(
            f"В план №{plan_id} не вошли заявки {numbers}: сначала решите по каждой — "
            "согласуйте другое время, перенесите на другой день или отмените"
        )

    # заявки плана переходят «Новая» -> «В плане»: переход системный, он должен быть в таблице
    await request_status_service.require_transition(
        session, RequestStatusId.NEW, RequestStatusId.PLANNED, manual=False
    )
    held_count, assigned_count, planned_ids = await plans_repository.hold_plan_requests(
        session, plan, clock.now()
    )
    if held_count != assigned_count:
        await session.rollback()
        raise PlanInUseError(
            f"План №{plan_id} устарел: часть его заявок уже закреплена за другим "
            "утверждённым планом, выполнена, отменена или уже в работе. Пересчитайте план "
            "на актуальных данных"
        )
    request_statuses_repository.add_history(
        session,
        planned_ids,
        RequestStatusId.NEW,
        RequestStatusId.PLANNED,
        manual=False,
        user_id=user_id,
        plan_id=plan.id,
        comment=f"План №{plan.id} утверждён",
    )
    try:
        await session.commit()
    except IntegrityError as error:
        # Частичный уникальный индекс окончательно разрешает гонку двух одновременных
        # утверждений одного дня. Превращаем техническую ошибку БД в понятный конфликт.
        await session.rollback()
        raise PlanInUseError(
            f"На {plan_date:%d.%m.%Y} одновременно был утверждён другой план; "
            "обновите список планов"
        ) from error
    return (await summarize_plans(session, [plan]))[0]


async def waiting_unassigned(session: AsyncSession, plan: Plan) -> list[Assignment]:
    """Не вошедшие в план заявки, которые всё ещё ждут планирования: «Новые», ничьи.

    Закреплённые за другим планом, снятые и отменённые сюда не попадают — по ним решать нечего.
    """
    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    return [
        a
        for a in assignments
        if a.engineer_id is None
        and a.request.status_id == RequestStatusId.NEW
        and a.request.approved_plan_id is None
    ]


def local_clock(moment: datetime) -> str:
    """Время по Москве часами и минутами: сообщения читают люди."""
    return moment.astimezone(local_timezone()).strftime("%H:%M")


def replan_routes(assigned: list) -> dict[int, list]:
    """Маршруты пересчёта по бригадам, визиты по порядку."""
    routes: dict[int, list] = defaultdict(list)
    for assignment in assigned:
        routes[assignment.engineer_id].append(assignment)
    for route in routes.values():
        route.sort(key=lambda assignment: assignment.visit_order or 0)
    return routes


async def brigades_at_work(session: AsyncSession, parent: Plan) -> dict[int, int]:
    """Кто сейчас занимается заявкой: бригада из отметки, а без отметки — из плана."""
    assignments = await plans_repository.list_plan_assignments(session, parent.id)
    at_work = {
        assignment.request_id: assignment.engineer_id
        for assignment in assignments
        if assignment.engineer_id is not None
    }
    facts = await brigade_repository.list_facts(session, list(at_work))
    at_work.update(
        {
            request_id: fact.engineer_id
            for request_id, fact in facts.items()
            if fact.engineer_id is not None
        }
    )
    return at_work


def started_as_planned(assignment, routes: dict[int, list], engineer_id: int | None, parent: Plan) -> bool:
    """Бригада уже занялась заявкой — но ровно так, как её ведёт пересчёт.

    Пока идёт расчёт, выезд бригадам не закрыт: они продолжают ехать по действующему плану и
    могут выехать раньше, чем оператор утвердит пересчёт. Если бригада уехала туда же, куда её
    ведёт пересчёт, и ничего не перепрыгнула, расхождения нет — пересчёт остаётся верным.
    """
    request = assignment.request
    if request.approved_plan_id != parent.id or request.status_id not in WORKED_STATUSES:
        return False
    if engineer_id != assignment.engineer_id:
        return False  # заявку взяла другая бригада, чем та, которой её отдал пересчёт
    for visit in routes.get(assignment.engineer_id, []):
        if visit.request_id == assignment.request_id:
            return True
        if visit.request.status_id in (RequestStatusId.NEW, RequestStatusId.PLANNED):
            return False  # впереди по маршруту есть незакрытая заявка: бригада поехала не туда
    return False


async def approve_replan(
    session: AsyncSession, plan: Plan, *, user_id: int | None = None
) -> PlanSummary:
    """Утверждает пересчёт с текущего момента: он заменяет пересчитанный план.

    - заявки, которые пересчёт разложил по маршрутам, и оставленные за бригадами (выполненные,
      отменённые, в работе) закрепляются за новым планом; «Новые» из них становятся «В плане»;
    - заявки прежнего плана «В плане», которым в пересчёте не нашлось места, — «Новая»,
      отвязываются: их окно нужно сдвинуть или заявку отменить, и пересчитать ещё раз;
    - прежний план помечается заменённым — бригады ездят уже по новому.
    Если с момента пересчёта бригады что-то отметили по заявкам, которые он раскладывал, —
    пересчёт устарел: считаем заново на актуальных данных.
    """
    parent = await plans_repository.get_plan(session, plan.parent_plan_id)
    current = await plans_repository.get_approved_plan(
        session, plan.plan_date, office_id=plan.office_id
    )
    if parent is None or current is None or current.id != parent.id:
        raise PlanInUseError(
            f"Пересчёт №{plan.id} устарел: действующий план дня уже не №{plan.parent_plan_id}. "
            "Пересчитайте действующий план заново"
        )

    # пересчёт вступает в силу в свой момент выезда (replan_autoapply). Если этот момент
    # заметно прошёл — сервер стоял, часы перевели, — маршруты начинаются в прошлом
    replanned_at = getattr(plan, "replanned_at", None)
    if replanned_at is not None:
        late = clock.now() - replanned_at
        if late > timedelta(minutes=settings.replan_grace_minutes):
            raise PlanInUseError(
                f"Пересчёт №{plan.id} не вступил в силу: он рассчитан на выезд с "
                f"{local_clock(replanned_at)}, а сейчас уже {local_clock(clock.now())} — "
                "бригады по нему опаздывают, ещё не выехав. Пересчитайте план заново"
            )

    # заявки дня на момент расчёта: пересчёт раскладывал именно их. Появились новые вводные,
    # пока считали и обзванивали, — план уже про другой день, нужен новый расчёт
    before = (plan.input_snapshot or {}).get("day_requests")
    if before:
        news = await day_state.new_since(session, parent, before)
        if news:
            raise PlanInUseError(
                f"Пересчёт №{plan.id} не вступил в силу: пока шли расчёт и обзвон, "
                f"{'; '.join(news)}. Пересчитайте план заново"
            )

    candidates = set((plan.input_snapshot or {}).get("request_order", []))
    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    assigned = [assignment for assignment in assignments if assignment.engineer_id is not None]
    routes = replan_routes(assigned)
    at_work = await brigades_at_work(session, parent)

    # пока считали и обзванивали, кто-то мог застрять: пересчёт исходил из того, что бригада
    # едет по плану, а она стоит. Про тех, кто выбился из плана ещё до расчёта, он уже знал
    replan_next = {
        engineer_id: visit.request_id
        for engineer_id, visit in nearest_open_visits(routes).items()
    }
    was_stuck = set((plan.input_snapshot or {}).get("stuck_brigades", []))
    now_stuck = await stuck_brigades(session, parent, replan_next)
    fresh_stuck = [name for engineer_id, name in now_stuck.items() if engineer_id not in was_stuck]
    if fresh_stuck:
        raise PlanInUseError(
            f"Пересчёт №{plan.id} не вступил в силу: пока шли расчёт и обзвон, из плана "
            f"выбились {', '.join(sorted(fresh_stuck))} — он считал, что они едут. "
            "Пересчитайте план заново"
        )
    to_plan, rebind, stale = [], [], []
    for assignment in assigned:
        request = assignment.request
        if assignment.request_id in candidates:
            # решатель раскладывал: заявка должна быть такой же, как в момент пересчёта
            if request.status_id == RequestStatusId.NEW and request.approved_plan_id is None:
                to_plan.append(request)
            elif (
                request.status_id == RequestStatusId.PLANNED
                and request.approved_plan_id == parent.id
            ):
                rebind.append(request)
            elif started_as_planned(assignment, routes, at_work.get(assignment.request_id), parent):
                rebind.append(request)  # бригада уехала туда же, куда её ведёт пересчёт
            else:
                stale.append(request.id)
        elif request.approved_plan_id == parent.id:
            rebind.append(request)  # оставлена за бригадой: выполнена, отменена или в работе
        else:
            stale.append(request.id)
    if stale:
        listed = ", ".join(f"№{request_id}" for request_id in sorted(stale))
        raise PlanInUseError(
            f"Пересчёт №{plan.id} устарел: после него менялись заявки {listed}. Пересчитайте ещё раз"
        )

    assigned_ids = {assignment.request_id for assignment in assigned}
    dropped = [
        request
        for request in await plans_repository.list_bound_requests(session, parent.id)
        if request.status_id == RequestStatusId.PLANNED and request.id not in assigned_ids
    ]

    await request_status_service.require_transition(
        session, RequestStatusId.NEW, RequestStatusId.PLANNED, manual=False
    )
    await request_status_service.require_transition(
        session, RequestStatusId.PLANNED, RequestStatusId.NEW, manual=False
    )
    statuses = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    now = clock.now()
    moment = planner_loader.planning_day(plan.plan_date).to_minutes(plan.replanned_at or now)
    at_text = f"{moment // 60:02d}:{moment % 60:02d}"

    # сначала заменяем прежний план: утверждённым на день может быть только один
    parent.superseded_at = now
    await session.flush()

    for request in rebind + to_plan:
        request.approved_plan_id = plan.id
    for request in to_plan:
        request_status_service.set_status(request, statuses[RequestStatusId.PLANNED])
    request_statuses_repository.add_history(
        session,
        [request.id for request in to_plan],
        RequestStatusId.NEW,
        RequestStatusId.PLANNED,
        manual=False,
        user_id=user_id,
        plan_id=plan.id,
        comment=f"Пересчёт №{plan.id} утверждён",
    )
    for request in dropped:
        request_status_service.set_status(request, statuses[RequestStatusId.NEW])
        request.approved_plan_id = None
    request_statuses_repository.add_history(
        session,
        [request.id for request in dropped],
        RequestStatusId.PLANNED,
        RequestStatusId.NEW,
        manual=False,
        user_id=user_id,
        plan_id=parent.id,
        comment=f"Не поместилась в пересчёт на {at_text}: сдвиньте окно или отмените",
    )
    plan.approved_at = now
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise PlanInUseError(
            f"На {plan.plan_date:%d.%m.%Y} одновременно был утверждён другой план; "
            "обновите список планов"
        ) from error
    return (await summarize_plans(session, [plan]))[0]


async def cancel_plan_approval(
    session: AsyncSession, plan_id: int, *, office_id: int, user_id: int | None = None
) -> PlanSummary:
    """Снимает утверждение: заявки плана снова доступны любому дню."""
    plan = await find_plan(session, plan_id, office_id=office_id)
    if getattr(plan, "superseded_at", None) is not None:
        raise PlanInUseError(
            f"План №{plan_id} заменён утверждённым пересчётом — снимайте утверждение с действующего"
        )
    if await plan_in_work(session, plan):
        raise PlanInUseError(
            f"По плану №{plan_id} уже работают: бригады видят его маршруты в приложении. "
            "Утверждение не снимают — пересчитайте план, и пересчёт его заменит"
        )
    if plan.approved_at is not None:
        # заявки «В плане» возвращаются в «Новые»: переход системный, он должен быть в таблице
        await request_status_service.require_transition(
            session, RequestStatusId.PLANNED, RequestStatusId.NEW, manual=False
        )
        released_ids = await plans_repository.release_plan_requests(session, plan)
        request_statuses_repository.add_history(
            session,
            released_ids,
            RequestStatusId.PLANNED,
            RequestStatusId.NEW,
            manual=False,
            user_id=user_id,
            plan_id=plan.id,
            comment=f"Утверждение плана №{plan.id} снято",
        )
        await session.commit()
    return (await summarize_plans(session, [plan]))[0]


async def check_planning_day(
    session: AsyncSession, plan_date: date, *, office_id: int
) -> PlanDayCheck:
    """Что ждёт диспетчера перед расчётом: сколько заявок дня и какие уже заняты другим днём."""
    day = planner_loader.planning_day(plan_date)
    requests = await requests_repository.list_active_requests_in_period(
        session, day.day_start, day.day_end, plan_date=plan_date, office_id=office_id
    )
    held = await requests_repository.list_requests_held_by_other_days(
        session, day.day_start, day.day_end, plan_date, office_id=office_id
    )
    approved = await plans_repository.get_approved_plan(session, plan_date, office_id=office_id)

    return PlanDayCheck(
        plan_date=plan_date,
        active_requests=len(requests),
        approved_plan_id=approved.id if approved else None,
        held_requests=[to_held_request(request, plan) for request, plan in held],
    )


def to_held_request(request: Request, plan: Plan) -> HeldRequest:
    """Исторический план без даты не должен попадать сюда, но не отдаём битый ответ API."""
    if plan.plan_date is None:
        raise PlanDataError([f"Утверждённый план №{plan.id} не содержит дату планирования"])
    return HeldRequest(
        request_id=request.id,
        address=request.address,
        window_start=request.window_start,
        window_end=request.window_end,
        plan_id=plan.id,
        plan_date=plan.plan_date,
    )


async def save_solution(
    session: AsyncSession,
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    *,
    run_type: PlanRunType = PlanRunType.OPTIMIZED,
    solver: str = SOLVER_NAME,
    solve_duration_ms: float | None = None,
    objective_order: tuple[ObjectiveCriterion, ...] | None = None,
    fixed: dict[int, list[Assignment]] | None = None,
) -> Plan:
    """fixed — пересчёт с текущего момента: визиты, которые бригада уже закрыла или начала,
    по бригадам. Они идут первыми в её маршруте нового плана с прежним временем, решатель их
    не двигает; новые визиты — после них."""
    day = loaded.day
    fixed = fixed or {}
    plan = plans_repository.add_plan(
        session,
        run_type,
        day.plan_date,
        solver,
        office_id=loaded.office_id,
        solve_duration_ms=(
            Decimal(str(round(solve_duration_ms, 3))) if solve_duration_ms is not None else None
        ),
        objective_policy=(
            {"criteria": [criterion.value for criterion in objective_order]}
            if objective_order is not None
            else None
        ),
    )
    plan.input_snapshot = snapshot_inputs(loaded)
    await session.flush()

    # пересчёт: что бригада уже закрыла или начала — первыми, с прежним временем
    for engineer_id, kept in fixed.items():
        for visit_order, assignment in enumerate(kept, start=1):
            plans_repository.add_assignment(
                session,
                {
                    "plan_id": plan.id,
                    "request_id": assignment.request_id,
                    "engineer_id": engineer_id,
                    "visit_order": visit_order,
                    "planned_arrival_time": assignment.planned_arrival_time,
                    "unassigned_reason": None,
                },
            )

    # назначенные заявки — по маршрутам исполнителей, в порядке объезда
    assigned_request_indices: set[int] = set()
    for engineer_index, visits in solution.routes.items():
        engineer = loaded.engineers[engineer_index]
        first_order = len(fixed.get(engineer.id, [])) + 1
        for visit_order, visit in enumerate(visits, start=first_order):
            plans_repository.add_assignment(
                session,
                {
                    "plan_id": plan.id,
                    "request_id": loaded.requests[visit.request_index].id,
                    "engineer_id": engineer.id,
                    "visit_order": visit_order,
                    "planned_arrival_time": day.from_minutes(visit.work_start_minute),
                    "unassigned_reason": None,
                },
            )
            assigned_request_indices.add(visit.request_index)

    # всё, что не попало ни в один маршрут, — неназначенные с причиной
    for request_index, request in enumerate(loaded.requests):
        if request_index in assigned_request_indices:
            continue
        plans_repository.add_assignment(
            session,
            {
                "plan_id": plan.id,
                "request_id": request.id,
                "engineer_id": None,
                "visit_order": None,
                "planned_arrival_time": None,
                "unassigned_reason": unassigned_reason(loaded, request_index),
            },
        )

    await session.flush()
    assigned_count = len(assigned_request_indices)
    unassigned = [
        unassigned_reason(loaded, index)
        for index in range(len(loaded.requests))
        if index not in assigned_request_indices
    ]
    await run_log.note(
        f"В план вошло {assigned_count} из "
        f"{run_log.plural(len(loaded.requests), 'заявки', 'заявок', 'заявок')}; "
        f"задействовано {run_log.plural(len(solution.routes), 'бригада', 'бригады', 'бригад')}",
        details={"assigned": assigned_count, "unassigned": len(unassigned)},
    )
    for reason, count in Counter(unassigned).most_common(3):
        await run_log.note(f"Не назначено {count}: {reason}", level="warning")
    return plan


def unassigned_reason(loaded: LoadedDay, request_index: int) -> str:
    """Почему заявка не назначена — понятным диспетчеру языком.

    Для совместимых исполнителей различаем невозможный отдельный первый выезд и
    конфликт с общим расписанием. Иначе уточняем, чего не хватило: навыка или транспорта.
    """
    candidates = loaded.instance.candidates(request_index)
    if candidates:
        if any(can_serve_as_first_visit(loaded, request_index, index) for index in candidates):
            return SCHEDULE_REASON
        return TIME_REASON

    request = loaded.requests[request_index]
    skill_name = loaded.skill_names.get(request.skill_id, f"№{request.skill_id}")
    engineers_with_skill = [
        engineer
        for engineer in loaded.engineers
        if request.skill_id in {skill.id for skill in engineer.skills}
    ]
    if not engineers_with_skill:
        return f"На этот день нет исполнителя с навыком «{skill_name}»"

    if request.transport_id is None:
        return SCHEDULE_REASON
    transport_name = loaded.transport_names.get(request.transport_id, f"№{request.transport_id}")
    return f"Исполнители с навыком «{skill_name}» есть, но ни у одного нет транспорта «{transport_name}»"


def can_serve_as_first_visit(loaded: LoadedDay, request_index: int, engineer_index: int) -> bool:
    """Успеет ли совместимый исполнитель выполнить заявку отдельным первым выездом."""
    instance = loaded.instance
    request = instance.requests[request_index]
    engineer = instance.engineers[engineer_index]
    travel = float(
        instance.travel_min[engineer.transport_id][
            instance.start_node(engineer_index), instance.request_node(request_index)
        ]
    )
    work_start = max(engineer.shift_start_min + travel, request.window_start_min)
    return (
        work_start <= request.window_end_min
        and work_start + request.duration_min <= engineer.shift_end_min
    )


async def list_plans(
    session: AsyncSession, plan_date: date | None, *, office_id: int
) -> list[PlanSummary]:
    plans = await plans_repository.list_plans(session, plan_date, office_id=office_id)
    return await summarize_plans(session, plans)


async def plan_in_work(session: AsyncSession, plan: Plan) -> bool:
    """По утверждённому плану уже работают: настал его день или бригада отметилась.

    Такой план снятием утверждения не трогают — маршрут пропал бы прямо у едущей бригады.
    Менять его можно только пересчётом (docs/algoV2.md).
    """
    if plan.approved_at is None or plan.plan_date is None:
        return False
    if plan.plan_date <= clock.now().astimezone(local_timezone()).date():
        return True
    return await plans_repository.has_brigade_marks(session, plan.id)


async def summarize_plans(session: AsyncSession, plans: list[Plan]) -> list[PlanSummary]:
    plan_ids = [plan.id for plan in plans]
    counts = await plans_repository.count_assignments_by_plan(session, plan_ids)
    assigned_request_ids = await plans_repository.assigned_request_ids_by_plan(session, plan_ids)
    # аварийные по справочнику: ими закрываются заявки, которых нет в снимке расчёта
    urgent_now = await requests_repository.urgent_request_ids(
        session,
        {request_id for ids in assigned_request_ids.values() for request_id in ids},
        TOP_PRIORITY_LEVEL,
    )
    replaced_by = await plans_repository.approved_replan_of(session, plan_ids)
    pending_replan = await plans_repository.pending_replan_of(session, plan_ids)
    # пересчёт, который не вступил в силу: у плана горит «!», пока день не пересчитают заново
    voided_replan = await plans_repository.voided_replan_of(session, plan_ids)
    # действующий утверждённый план каждого дня: по нему видно, какие черновики уже неактуальны
    active_by_day = {
        plan.plan_date: await plans_repository.get_approved_plan(
            session, plan.plan_date, office_id=plan.office_id
        )
        for plan in plans
        if plan.plan_date is not None
    }
    summaries = []
    for plan in plans:
        engineers_used, assigned, unassigned = counts.get(plan.id, (0, 0, 0))
        active = active_by_day.get(plan.plan_date)
        # черновик, который уже не утвердить: на его день действует другой план, и это не
        # пересчёт этого плана. Такой расчёт — история, его не с чем сверять
        outdated = (
            plan.approved_at is None
            and active is not None
            and getattr(plan, "parent_plan_id", None) != active.id
        )
        # обещания сверяем только с тем, что ещё в игре: заменённый план и устаревший черновик
        # физически не могли учесть обещание, данное после них
        live = not outdated and getattr(plan, "superseded_at", None) is None
        urgent_assigned_count = count_urgent_assignments(
            plan.input_snapshot, assigned_request_ids.get(plan.id, set()), urgent_now
        )
        summaries.append(
            PlanSummary(
                id=plan.id,
                run_type=plan.run_type.value,
                plan_date=plan.plan_date,
                solver=plan.solver,
                created_at=plan.created_at,
                engineers_used=engineers_used,
                assigned_count=assigned,
                urgent_assigned_count=urgent_assigned_count,
                unassigned_count=unassigned,
                total_distance_km=float(plan.total_distance_km)
                if plan.total_distance_km is not None
                else None,
                distance_provider=plan.distance_provider,
                solve_duration_ms=(
                    float(plan.solve_duration_ms) if plan.solve_duration_ms is not None else None
                ),
                approved_at=plan.approved_at,
                objective_order=objective_order_from_plan(plan),
                parent_plan_id=getattr(plan, "parent_plan_id", None),
                replanned_at=getattr(plan, "replanned_at", None),
                voided_at=getattr(plan, "voided_at", None),
                void_reason=getattr(plan, "void_reason", None),
                superseded_at=getattr(plan, "superseded_at", None),
                replaced_by_plan_id=replaced_by.get(plan.id),
                pending_replan_id=(
                    pending_replan.get(plan.id) if plan.approved_at is not None else None
                ),
                voided_replan_id=(voided.id if (voided := voided_replan.get(plan.id)) else None),
                voided_replan_reason=(voided.void_reason if voided else None),
                decisions_from_plan_id=getattr(plan, "decisions_from_plan_id", None),
                decisions_count=getattr(plan, "decisions_count", None),
                can_cancel_approval=(
                    plan.approved_at is not None
                    and getattr(plan, "superseded_at", None) is None
                    and not await plan_in_work(session, plan)
                ),
                outdated=outdated,
                broken_promises=await broken_promises(session, plan) if live else [],
                **(await replan_reasons(session, plan)),
            )
        )
    return summaries


def nearest_open_visits(routes: dict[int, list]) -> dict[int, Assignment]:
    """Ближайший незакрытый визит каждой бригады по её маршруту: {бригада: визит}."""
    nearest = {}
    for engineer_id, route in routes.items():
        visit = next(
            (
                assignment
                for assignment in route
                if assignment.request.status_id
                in (RequestStatusId.NEW, RequestStatusId.PLANNED)
            ),
            None,
        )
        if visit is not None:
            nearest[engineer_id] = visit
    return nearest


async def replan_next_visits(session: AsyncSession, plan_id: int) -> dict[int, int] | None:
    """Куда посчитанный пересчёт ведёт каждую бригаду прямо сейчас: {бригада: заявка}.

    Пересчёт считался на выезд через запас, и до этого момента бригады едут по действующему
    плану. Выехать можно туда, куда их ведёт и новый план: тогда расхождения не будет, и
    утверждение такой выезд принимает (approve_replan.started_as_planned). None — пересчёта нет.
    """
    replan_id = await plans_repository.unapproved_replan_id(session, plan_id)
    if replan_id is None:
        return None
    assignments = await plans_repository.list_plan_assignments(session, replan_id)
    routes = replan_routes([a for a in assignments if a.engineer_id is not None])
    return {
        engineer_id: visit.request_id
        for engineer_id, visit in nearest_open_visits(routes).items()
    }


async def stuck_brigades(
    session: AsyncSession, plan: Plan, replan_next: dict[int, int] | None = None
) -> dict[int, str]:
    """Бригады, которые сейчас выбились из плана: {бригада: имя}.

    Выбилась — то же, что закрывает ей выезд (departure_gate): не отметила «Выехали» через
    departure_grace_minutes после планового начала работ или к окну ближайшей заявки уже не
    успеть. Бригаду, которую новый план ведёт не туда, куда она собиралась, не считаем: она
    стоит не сама по себе, а потому что мы закрыли ей выезд на время пересчёта.
    """
    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    assigned = [assignment for assignment in assignments if assignment.engineer_id is not None]
    facts = await brigade_repository.list_facts(
        session, [assignment.request_id for assignment in assigned]
    )
    delays = await plan_route_delays(session, plan, assigned)
    stuck = {}
    for engineer_id, visit in nearest_open_visits(replan_routes(assigned)).items():
        if sends_elsewhere(replan_next, engineer_id, visit.request_id):
            continue
        fact = facts.get(visit.request_id)
        delay = delays.get(engineer_id)
        check = departure_gate.check_departure(
            planned_start=visit.planned_arrival_time,
            departed_at=fact.departed_at if fact is not None else None,
            at_risk=delay is not None and visit.request_id in delay.at_risk_request_ids,
            allowed_at=visit.request.departure_allowed_at,
            replan_sends_elsewhere=False,
            now=clock.now(),
        )
        if not check.allowed:
            stuck[engineer_id] = visit.engineer.name if visit.engineer is not None else ""
    return stuck


def sends_elsewhere(replan_next: dict[int, int] | None, engineer_id: int, request_id: int) -> bool:
    """Пересчёт ждёт утверждения и ведёт эту бригаду не на эту заявку."""
    return replan_next is not None and replan_next.get(engineer_id) != request_id


def set_waiting(route: EngineerRoute, facts: dict, replan_next: dict[int, int] | None) -> None:
    """Бригада ждёт нового плана: выезд на ближайшую незакрытую заявку закрыт."""
    next_visit = next(
        (
            visit
            for visit in route.visits
            if visit.status_id in (RequestStatusId.NEW, RequestStatusId.PLANNED)
        ),
        None,
    )
    if next_visit is None:
        return
    fact = facts.get(next_visit.request_id)
    check = departure_gate.check_departure(
        planned_start=next_visit.planned_arrival_time,
        departed_at=fact.departed_at if fact else None,
        at_risk=next_visit.request_id in route.at_risk_request_ids,
        allowed_at=next_visit.departure_allowed_at,
        replan_sends_elsewhere=sends_elsewhere(
            replan_next, route.engineer_id, next_visit.request_id
        ),
        now=clock.now(),
    )
    if not check.allowed:
        # оператору нужно, с какого времени бригада стоит и к какой заявке она не выехала
        since = next_visit.planned_arrival_time.astimezone(local_timezone()).strftime("%H:%M")
        cause = departure_gate.OPERATOR_REASON.get(check.reason, check.reason)
        route.waiting_request_id = next_visit.request_id
        route.waiting_reason = f"с {since} · {cause} · ближайшая заявка №{next_visit.request_id}"
        # то же по частям: интерфейс собирает одну строку вместе с опозданием, без повторов
        route.waiting_since = next_visit.planned_arrival_time
        route.waiting_cause = departure_gate.REASON_CODE.get(check.reason)


async def allow_departure(
    session: AsyncSession, plan_id: int, request_id: int, *, office_id: int, user_id: int | None
) -> PlanDetail:
    """Оператор отпускает отстающую бригаду: клиент согласился подождать (docs/algoV2.md)."""
    plan = await find_plan(session, plan_id, office_id=office_id)
    request = await requests_repository.get_request(session, request_id)
    if request is None or request.office_id != office_id or request.approved_plan_id != plan.id:
        raise PlanDataError([f"заявки №{request_id} нет в маршрутах плана №{plan_id}"])
    request.departure_allowed_at = clock.now()
    request_statuses_repository.add_history(
        session,
        [request.id],
        request.status_id,
        request.status_id,
        manual=True,
        user_id=user_id,
        plan_id=plan.id,
        comment="Оператор разрешил выезд: клиент согласился подождать",
    )
    await session.commit()
    return await get_plan_detail(session, plan_id, office_id=office_id)


async def broken_promises(session: AsyncSession, plan: Plan) -> list[BrokenPromise]:
    """Обещания клиентам, которые этот расчёт не удержал (docs/algoV2.md, шаг 5).

    Заявку согласовали на время: она должна стоять в плане и начинаться внутри обещанного
    окна. Не попала или уехала — оператор увидит это до утверждения и решит сам.
    """
    assignments = await plans_repository.list_plan_assignments(session, plan.id)
    promised = [
        assignment
        for assignment in assignments
        if assignment.request is not None and assignment.request.promised_from is not None
    ]
    broken = []
    for assignment in promised:
        request = assignment.request
        start = assignment.planned_arrival_time if assignment.engineer_id is not None else None
        kept = start is not None and request.promised_from <= start <= request.promised_to
        if not kept:
            broken.append(
                BrokenPromise(
                    request_id=request.id,
                    address=request.address,
                    promised_from=request.promised_from,
                    promised_to=request.promised_to,
                    planned_start=start,
                )
            )
    return broken


async def replan_reasons(session: AsyncSession, plan: Plan) -> dict[str, list]:
    """Что изменилось у утверждённого плана с утверждения: снятые заявки и новые заявки дня.

    Если есть и то, и другое — план стоит пересчитать. У неутверждённого плана считать нечего:
    он и так пересчитывается свободно.
    """
    if plan.approved_at is None or plan.plan_date is None or getattr(plan, "superseded_at", None):
        return {}
    withdrawn = await plans_repository.list_withdrawn_requests(session, plan.id)
    day = planner_loader.planning_day(plan.plan_date)
    day_requests = await requests_repository.list_active_requests_in_period(
        session, day.day_start, day.day_end, plan_date=plan.plan_date, office_id=plan.office_id
    )
    seen = await plans_repository.plan_request_ids(session, plan.id)
    new_requests = [
        request
        for request in day_requests
        if request.status_id == RequestStatusId.NEW
        and request.approved_plan_id is None
        and request.id not in seen
    ]
    # новые аварии — отдельно: по ним маршрут бригады меняют посреди дня
    top_level = {
        priority.id
        for priority in await references_repository.list_priorities(session)
        if priority.level == TOP_PRIORITY_LEVEL
    }
    delays = await plan_route_delays(session, plan)
    return {
        "new_request_ids": [request.id for request in new_requests],
        "urgent_request_ids": [
            request.id for request in new_requests if request.priority_id in top_level
        ],
        "at_risk_request_ids": sorted(
            request_id for delay in delays.values() for request_id in delay.at_risk_request_ids
        ),
        "withdrawn_requests": [
            WithdrawnRequest(request_id=request_id, status_id=status_id)
            for request_id, status_id in withdrawn
        ],
    }


def objective_order_from_plan(plan: Plan) -> list[ObjectiveCriterion] | None:
    policy = getattr(plan, "objective_policy", None)
    if not policy:
        return None
    try:
        return list(
            validate_objective_order([ObjectiveCriterion(value) for value in policy["criteria"]])
        )
    except (KeyError, TypeError, ValueError):
        return None


def count_urgent_assignments(
    snapshot: dict | None, assigned_request_ids: set[int], urgent_now: set[int]
) -> int:
    """Сколько аварийных заявок в плане.

    Считаем по снимку расчёта: в нём заявка такая, какой её видел решатель. Заявки, которой
    в снимке нет, в этом расчёте и не было — так бывает у пересчёта, который забрал
    выполненные и начатые заявки из прежнего плана. Для них берём признак из справочника
    (urgent_now), иначе у пересчётов колонка «Авар.» оставалась пустой.
    """
    requests = (snapshot or {}).get("requests") or {}
    urgent = 0
    for request_id in assigned_request_ids:
        request = requests.get(str(request_id))
        if request is not None and "is_urgent" in request:
            urgent += bool(request["is_urgent"])
        else:
            urgent += request_id in urgent_now
    return urgent


async def get_plan_detail(session: AsyncSession, plan_id: int, *, office_id: int) -> PlanDetail:
    """План с маршрутами: порядок визитов, пробег и линия каждого маршрута, неназначенные заявки."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None or plan.office_id != office_id:
        raise PlanNotFoundError(f"План №{plan_id} не найден")

    stored_assignments = await plans_repository.list_plan_assignments(session, plan_id)
    assignments: list[AssignmentView] = list(stored_assignments)
    if plan.input_snapshot:
        assignments = [snapshot_assignment(a, plan.input_snapshot) for a in stored_assignments]
    unassigned = [
        to_unassigned_request(assignment)
        for assignment in assignments
        if assignment.engineer is None or assignment.engineer_id is None
    ]
    # маршруты — готовые из кеша плана; строятся, только если их там нет (старые планы)
    routes, built = await plan_routes(session, plan, stored_assignments)
    if built:
        await session.commit()

    # отметки бригад из мобильного приложения — факт поверх плана, и отставание от него
    facts = await brigade_repository.list_facts(
        session, [assignment.request_id for assignment in stored_assignments]
    )
    delays = await plan_route_delays(session, plan, stored_assignments)
    phones = await brigades_repository.phones_by_engineer(
        session, [route.engineer_id for route in routes]
    )
    replan_next = await replan_next_visits(session, plan.id)
    for route in routes:
        route.phone = phones.get(route.engineer_id)
        if route.engineer_id in delays:
            route.delay_minutes = delays[route.engineer_id].delay_minutes
            route.at_risk_request_ids = delays[route.engineer_id].at_risk_request_ids
        set_waiting(route, facts, replan_next)
        for visit in route.visits:
            fact = facts.get(visit.request_id)
            if fact is not None:
                visit.departed_at = fact.departed_at
                visit.arrived_at = fact.arrived_at
                visit.finished_at = fact.finished_at

    summary = (await summarize_plans(session, [plan]))[0]
    return PlanDetail(
        **summary.model_dump(exclude={"total_distance_km"}),
        total_distance_km=round(sum(route.distance_km for route in routes), 3),
        routes=list(routes),
        unassigned=unassigned,
    )


async def plan_route_delays(
    session: AsyncSession, plan: Plan, assignments: list[Assignment] | None = None
) -> dict[int, RouteDelay]:
    """Отставание каждой бригады утверждённого плана по её отметкам (route_delay.py).

    «Сейчас» учитывается только у плана на сегодня — у прошлых и будущих дней только отметки.
    """
    if plan.approved_at is None or plan.plan_date is None or getattr(plan, "superseded_at", None):
        return {}
    if assignments is None:
        assignments = await plans_repository.list_plan_assignments(session, plan.id)
    facts = await brigade_repository.list_facts(
        session, [assignment.request_id for assignment in assignments]
    )
    codes = {
        status.id: status.code
        for status in await request_statuses_repository.list_statuses(session)
    }
    moment = clock.now()
    now = moment if planner_loader.local_date_of(moment) == plan.plan_date else None

    routes: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        if assignment.engineer_id is not None and assignment.planned_arrival_time is not None:
            routes[assignment.engineer_id].append(assignment)
    result = {}
    for engineer_id, route in routes.items():
        visits = []
        for assignment in sorted(route, key=lambda item: item.visit_order or 0):
            request = assignment.request
            fact = facts.get(request.id)
            arrived_at = fact.arrived_at if fact else None
            visits.append(
                VisitFact(
                    request_id=request.id,
                    planned_start=assignment.planned_arrival_time,
                    duration_minutes=request.duration_minutes,
                    window_end=request.window_end,
                    state=visit_state(
                        codes.get(request.status_id, ""),
                        request.approved_plan_id != plan.id,
                        arrived_at,
                    ),
                    arrived_at=arrived_at,
                    finished_at=fact.finished_at if fact else None,
                )
            )
        result[engineer_id] = route_delay(visits, now)
    return result


def candidate_engineers_by_request(snapshot: dict | None) -> dict[int, int]:
    """Сколько исполнителей дня подходили под каждую заявку: навык и требуемый транспорт.

    Считается по снимку плана — тем данным, на которых план и строился.
    """
    if not snapshot or "requests" not in snapshot or "engineers" not in snapshot:
        return {}

    engineers = list(snapshot["engineers"].values())
    counts = {}
    for request in snapshot["requests"].values():
        counts[request["id"]] = sum(
            1
            for engineer in engineers
            if request["skill_id"] in engineer["skill_ids"]
            and (
                request["transport_id"] is None
                or request["transport_id"] == engineer["transport_id"]
            )
        )
    return counts


def route_request(
    ordered: list[AssignmentView],
) -> tuple[list[Point], TransportKind, list[datetime] | None]:
    """По чему строится маршрут бригады: старт, заявки по порядку и, для общественного
    транспорта, время отправления на каждом плече — расписание зависит от него."""
    engineer = ordered[0].engineer
    points = [
        Point(latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude))
    ]
    points += [
        Point(
            latitude=float(assignment.request.latitude),
            longitude=float(assignment.request.longitude),
        )
        for assignment in ordered
    ]
    transport = TransportKind(engineer.transport_id)
    if transport is not TransportKind.PUBLIC_TRANSPORT:
        return points, transport, None
    departures = [engineer.shift_start]
    departures += [
        assigned_arrival_time(assignment) + timedelta(minutes=assignment.request.duration_minutes)
        for assignment in ordered[:-1]
    ]
    return points, transport, departures


# версия разбора маршрута на плечи: меняется, когда меняется сам ответ (например, у
# велосипедных плеч появился свой режим). Старые сохранённые маршруты тогда пересчитываются
ROUTE_FORMAT_VERSION = 2


def route_fingerprint(
    points: list[Point], transport: TransportKind, departures: list[datetime] | None
) -> str:
    """Отпечаток маршрута: совпал — готовый маршрут годится, не совпал — строим заново."""
    source = {
        "version": ROUTE_FORMAT_VERSION,
        "transport": transport.value,
        "points": [[round(point.latitude, 6), round(point.longitude, 6)] for point in points],
        "departures": [moment.isoformat() for moment in departures or []],
    }
    return hashlib.sha1(json.dumps(source).encode()).hexdigest()


async def route_travel(
    ordered: list[AssignmentView], cached: dict, *, strict: bool
) -> tuple[TravelRoute, str, bool]:
    """Маршрут бригады: из кеша плана, если он строился по тем же точкам, иначе — заново.

    strict — расчёт плана: без R5 честного пробега ОТ нет, поэтому ошибка, а не оценка.
    Возвращает маршрут, его отпечаток и признак, что он построен только что.
    """
    points, transport, departures = route_request(ordered)
    fingerprint = route_fingerprint(points, transport, departures)
    entry = cached.get(ordered[0].engineer.id)
    if entry is not None and entry.fingerprint == fingerprint:
        return TravelRoute.model_validate(entry.travel), fingerprint, False
    if departures is None:
        return await build_route(points, transport), fingerprint, True
    try:
        travel = await build_route(
            points, transport, leg_departure_times=departures, allow_fallback=not strict
        )
    except (httpx.HTTPError, KeyError, ValueError) as error:
        if not strict:
            raise
        raise ExternalServiceError(f"R5 не смог построить маршрут плана: {error}") from error
    return travel, fingerprint, True


async def plan_routes(
    session: AsyncSession,
    plan: Plan,
    stored_assignments: list[Assignment] | None = None,
    *,
    strict: bool = False,
) -> tuple[list[EngineerRoute], bool]:
    """Маршруты всех бригад плана: линия для карты, участки и пробег.

    Маршрутизатор на большом дне отвечает минутами, поэтому готовые маршруты лежат в plan_route
    (db/init/042): расчёт строит их один раз, открытие плана берёт готовые. Возвращает маршруты
    и признак, что какие-то из них построены сейчас и записаны в кеш — их надо сохранить.
    """
    if stored_assignments is None:
        stored_assignments = await plans_repository.list_plan_assignments(session, plan.id)
    assignments: list[AssignmentView] = list(stored_assignments)
    if plan.input_snapshot:
        assignments = [snapshot_assignment(a, plan.input_snapshot) for a in stored_assignments]
    by_engineer: dict[int, list[AssignmentView]] = defaultdict(list)
    for assignment in assignments:
        if assignment.engineer is not None and assignment.engineer_id is not None:
            by_engineer[assignment.engineer_id].append(assignment)
    groups = [
        sorted(group, key=assigned_visit_order)
        for group in sorted(by_engineer.values(), key=assigned_engineer_name)
    ]
    for group in groups:
        if any(a.visit_order is None or a.planned_arrival_time is None for a in group):
            raise ValueError("назначенный маршрут содержит неполные данные")

    cached = await plans_repository.list_cached_routes(session, plan.id)
    # плечи маршрутов обычно уже спрошены проверкой расписания — берутся из кеша R5
    with travel_cache.counting() as counters:
        travels = await asyncio.gather(
            *(route_travel(group, cached, strict=strict) for group in groups)
        )
    if counters.from_cache or counters.from_r5:
        await run_log.note(
            f"Плечи маршрутов: из кеша {counters.from_cache}, запросов к R5 {counters.from_r5}"
        )
    built = False
    for group, (travel, fingerprint, fresh) in zip(groups, travels, strict=True):
        if fresh:
            built = True
            await plans_repository.save_cached_route(
                session, plan.id, group[0].engineer.id, fingerprint, travel.model_dump(mode="json")
            )
    candidates_by_request = candidate_engineers_by_request(plan.input_snapshot)
    routes = [
        build_engineer_route(group, candidates_by_request, travel)
        for group, (travel, _, _) in zip(groups, travels, strict=True)
    ]
    return routes, built


# оценки вместо маршрута: маршрутизатор не ответил, и пробег посчитан приближённо
APPROXIMATE_PROVIDERS = {TravelProvider.HAVERSINE.value, TravelProvider.TRANSIT_ESTIMATE.value}


def routes_distance(routes: list[EngineerRoute]) -> PlanDistance:
    """Пробег плана — сумма маршрутов бригад и чем он посчитан.

    Valhalla (дороги) и R5 (расписание ОТ) — оба настоящий расчёт, поэтому их смесь — не
    «приближённо», а «routed». «mixed» — только когда часть маршрутов досталась оценке.
    """
    providers = {route.provider for route in routes}
    if not providers:
        provider = None
    elif len(providers) == 1:
        provider = providers.pop()
    elif providers & APPROXIMATE_PROVIDERS:
        provider = "mixed"
    else:
        provider = "routed"
    return PlanDistance(
        distance_km=round(sum(route.distance_km for route in routes), 3), provider=provider
    )


def build_engineer_route(
    ordered: list[AssignmentView], candidates_by_request: dict[int, int], travel: TravelRoute
) -> EngineerRoute:
    """Маршрут одного исполнителя из уже построенного пути: визиты по порядку, пробег и линия.

    Пробег берётся из маршрутизатора (/route) по порядку визитов, а не из матрицы:
    матрица приближённая и занижает длинные плечи.
    """
    engineer = ordered[0].engineer
    return EngineerRoute(
        engineer_id=engineer.id,
        engineer_name=engineer.name,
        transport_id=engineer.transport_id,
        start_latitude=float(engineer.start_latitude),
        start_longitude=float(engineer.start_longitude),
        distance_km=travel.distance_km,
        duration_min=travel.duration_min,
        provider=travel.provider.value,
        geometry=travel.geometry,
        legs=travel.legs,
        shift_start=engineer.shift_start,
        shift_end=engineer.shift_end,
        visits=route_visits(ordered, engineer, candidates_by_request),
    )


def route_visits(
    ordered: list[AssignmentView],
    engineer: Engineer | SimpleNamespace,
    candidates_by_request: dict[int, int],
) -> list[PlanVisit]:
    """Визиты по порядку; каждый знает, когда исполнитель освободился до него."""
    visits = []
    available_from = engineer.shift_start
    for assignment in ordered:
        visits.append(
            to_plan_visit(
                assignment,
                available_from=available_from,
                shift_end=engineer.shift_end,
                candidate_engineers=candidates_by_request.get(assignment.request.id),
            )
        )
        available_from = assigned_arrival_time(assignment) + timedelta(
            minutes=assignment.request.duration_minutes
        )
    return visits


def assigned_engineer_name(assignments: list[AssignmentView]) -> str:
    """Ключ сортировки маршрутов; назначение по ограничению БД всегда имеет инженера."""
    engineer = assignments[0].engineer
    if engineer is None:
        raise ValueError("у маршрута нет исполнителя")
    return str(engineer.name)


def assigned_visit_order(assignment: AssignmentView) -> int:
    """Ключ сортировки визитов; у назначенной строки порядок не может быть NULL."""
    if assignment.visit_order is None:
        raise ValueError("у назначения нет порядка посещения")
    return int(assignment.visit_order)


def assigned_arrival_time(assignment: AssignmentView) -> datetime:
    """Время визита назначенной строки; NULL допустим только у неназначенной заявки."""
    if assignment.planned_arrival_time is None:
        raise ValueError("у назначения нет времени прибытия")
    return assignment.planned_arrival_time


def to_plan_visit(
    assignment: AssignmentView,
    *,
    available_from: datetime,
    shift_end: datetime,
    candidate_engineers: int | None,
) -> PlanVisit:
    """Визит с фактами: когда исполнитель освободился и сколько осталось запаса."""
    if assignment.visit_order is None or assignment.planned_arrival_time is None:
        raise ValueError("назначение содержит неполные данные")
    request = assignment.request
    work_start = assignment.planned_arrival_time
    work_end = work_start + timedelta(minutes=request.duration_minutes)
    return PlanVisit(
        visit_order=assignment.visit_order,
        request_id=request.id,
        planned_arrival_time=assignment.planned_arrival_time,
        address=request.address,
        latitude=float(request.latitude),
        longitude=float(request.longitude),
        window_start=request.window_start,
        window_end=request.window_end,
        duration_minutes=request.duration_minutes,
        priority_id=request.priority_id,
        status_id=request.status_id,
        approved_plan_id=request.approved_plan_id,
        available_from=available_from,
        window_slack_minutes=round((request.window_end - work_start).total_seconds() / 60),
        shift_slack_minutes=round((shift_end - work_end).total_seconds() / 60),
        candidate_engineers=candidate_engineers,
        departure_allowed_at=getattr(request, "departure_allowed_at", None),
    )


def to_unassigned_request(assignment: AssignmentView) -> UnassignedRequest:
    request = assignment.request
    return UnassignedRequest(
        request_id=request.id,
        address=request.address,
        latitude=float(request.latitude),
        longitude=float(request.longitude),
        window_start=request.window_start,
        window_end=request.window_end,
        reason=assignment.unassigned_reason,
    )


def snapshot_inputs(loaded: LoadedDay) -> dict:
    requests = {
        str(r.id): {
            "id": r.id,
            "address": r.address,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "window_start": r.window_start.isoformat(),
            "window_end": r.window_end.isoformat(),
            "duration_minutes": r.duration_minutes,
            "priority_id": r.priority_id,
            "skill_id": r.skill_id,
            "transport_id": r.transport_id,
            "is_urgent": loaded.instance.requests[index].is_urgent,
        }
        for index, r in enumerate(loaded.requests)
    }
    engineers = {
        str(e.id): {
            "id": e.id,
            "name": e.name,
            "start_latitude": float(e.start_latitude),
            "start_longitude": float(e.start_longitude),
            "transport_id": e.transport_id,
            "shift_start": e.shift_start.isoformat(),
            "shift_end": e.shift_end.isoformat(),
            "skill_ids": [skill.id for skill in e.skills],
        }
        for e in loaded.engineers
    }
    return {
        "requests": requests,
        "engineers": engineers,
        "request_order": [r.id for r in loaded.requests],
        "engineer_order": [e.id for e in loaded.engineers],
    }


def snapshot_assignment(assignment: Assignment, snapshot: dict) -> Assignment | SimpleNamespace:
    """Заявка и исполнитель такими, какими они были при расчёте плана.

    Если заявки нет в снимке (её добавили или перенумеровали после расчёта), показываем
    текущие данные: лучше показать план по живым данным, чем не показать вовсе.
    """
    if str(assignment.request_id) not in snapshot["requests"]:
        return assignment

    request = dict(snapshot["requests"][str(assignment.request_id)])
    for key in ("window_start", "window_end"):
        request[key] = datetime.fromisoformat(request[key])
    # статус и закрепление за планом — не данные расчёта, а то, что с заявкой сейчас: берём живыми
    request["status_id"] = assignment.request.status_id
    request["approved_plan_id"] = assignment.request.approved_plan_id

    # в снимке время лежит строками; смена нужна временем — по ней считается запас визита
    engineer = snapshot["engineers"].get(str(assignment.engineer_id))
    if engineer is not None:
        engineer = dict(engineer)
        for key in ("shift_start", "shift_end"):
            engineer[key] = datetime.fromisoformat(engineer[key])

    return SimpleNamespace(
        request=SimpleNamespace(**request),
        engineer=SimpleNamespace(**engineer) if engineer else None,
        engineer_id=assignment.engineer_id,
        visit_order=assignment.visit_order,
        planned_arrival_time=assignment.planned_arrival_time,
        unassigned_reason=assignment.unassigned_reason,
    )
