"""Построение сравнимой пары baseline/cuOpt, сохранение и просмотр планов."""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, NotFoundError
from src.core.local_day import intersected_local_dates
from src.models import Assignment, Plan, PlanRunType
from src.repositories.plans import plans_repository
from src.repositories.requests import requests_repository
from src.schemas.plans import (
    EngineerRoute,
    PlanDetail,
    PlanningDayOption,
    PlanSummary,
    PlanVisit,
    UnassignedRequest,
)
from src.schemas.travel import Point, TransportKind, TravelProvider
from src.services.planner import baseline_solver, cuopt_solver, planner_loader
from src.services.planner.planner_loader import LoadedDay
from src.services.travel import build_route

SOLVER_NAME = "cuopt"
BASELINE_SOLVER_NAME = "baseline"
AssignmentView = Assignment | SimpleNamespace

SCHEDULE_REASON = (
    "Подходящий исполнитель может выполнить заявку отдельно, но она не поместилась "
    "в общий план с учётом срочности, других заявок, времени дороги и смен"
)
TIME_REASON = (
    "Подходящие исполнители есть, но ни один не успевает приехать от начала смены, "
    "начать работу в окне заявки и закончить её до конца смены"
)


class PlanNotFoundError(NotFoundError):
    """Плана с таким номером нет."""


class PlanDataError(DataError):
    """План на этот день построить нельзя."""


async def list_planning_days(session: AsyncSession) -> list[PlanningDayOption]:
    """Московские дни, с которыми пересекаются окна активных заявок."""
    requests = await requests_repository.list_active_requests(session)
    request_count_by_day: dict[date, int] = defaultdict(int)
    for request in requests:
        for plan_date in intersected_local_dates(request.window_start, request.window_end):
            request_count_by_day[plan_date] += 1
    return [
        PlanningDayOption(plan_date=plan_date, active_requests=count)
        for plan_date, count in sorted(request_count_by_day.items())
    ]


async def load_planning_day(session: AsyncSession, plan_date: date) -> LoadedDay:
    """Загружает данные дня и проверяет наличие заявок и исполнителей."""
    day = planner_loader.planning_day(plan_date)
    loaded = await planner_loader.load_day(session, day)
    if loaded.instance.n_requests == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет активных заявок"])
    if loaded.instance.n_engineers == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет исполнителей со сменой"])

    return loaded


async def build_plan_for_day(session: AsyncSession, plan_date: date) -> PlanSummary:
    loaded = await load_planning_day(session, plan_date)

    baseline_started = time.perf_counter()
    baseline_solution = baseline_solver.solve_day(loaded.instance)
    baseline_duration_ms = (time.perf_counter() - baseline_started) * 1000

    optimized_started = time.perf_counter()
    solution = await cuopt_solver.solve_day(loaded.instance)
    optimized_duration_ms = (time.perf_counter() - optimized_started) * 1000

    comparison_id = uuid4()
    baseline_plan = await save_solution(
        session,
        loaded,
        baseline_solution,
        run_type=PlanRunType.BASELINE,
        solver=BASELINE_SOLVER_NAME,
        comparison_id=comparison_id,
        solve_duration_ms=baseline_duration_ms,
    )
    plan = await save_solution(
        session,
        loaded,
        solution,
        run_type=PlanRunType.OPTIMIZED,
        solver=SOLVER_NAME,
        comparison_id=comparison_id,
        solve_duration_ms=optimized_duration_ms,
    )
    baseline_distance, optimized_distance = await asyncio.gather(
        total_route_distance(loaded, baseline_solution),
        total_route_distance(loaded, solution),
    )
    set_plan_distance(baseline_plan, baseline_distance)
    set_plan_distance(plan, optimized_distance)
    await session.commit()
    return (await summarize_plans(session, [plan]))[0]


@dataclass(frozen=True)
class PlanDistance:
    distance_km: float
    provider: str | None


def set_plan_distance(plan: Plan, distance: PlanDistance) -> None:
    plan.total_distance_km = Decimal(str(distance.distance_km))
    plan.distance_provider = distance.provider


async def total_route_distance(
    loaded: LoadedDay, solution: cuopt_solver.DaySolution
) -> PlanDistance:
    """Общий пробег плана по дорогам — так же, как в просмотре плана: по /route от старта
    исполнителя через его заявки по порядку. Сохраняется в план, чтобы список планов
    показывал пробег без пересчёта маршрутов."""

    async def route_distance(
        engineer_index: int, visits: list[cuopt_solver.PlannedVisit]
    ) -> tuple[float, str]:
        engineer = loaded.engineers[engineer_index]
        points = [
            Point(
                latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude)
            )
        ]
        points += [
            Point(
                latitude=float(loaded.requests[visit.request_index].latitude),
                longitude=float(loaded.requests[visit.request_index].longitude),
            )
            for visit in visits
        ]
        # TODO: сделать fallback управляемым: retry/cached route и сохранять источник
        # отдельно для каждого маршрута. Пока хотя бы честно помечаем весь пробег плана.
        travel = await build_route(points, TransportKind(engineer.transport_id))
        provider = (
            travel.provider.value
            if isinstance(travel.provider, TravelProvider)
            else str(travel.provider)
        )
        return travel.distance_km, provider

    routes = await asyncio.gather(
        *(
            route_distance(engineer_index, visits)
            for engineer_index, visits in solution.routes.items()
            if visits
        )
    )
    providers = {provider for _, provider in routes}
    provider = providers.pop() if len(providers) == 1 else "mixed" if providers else None
    return PlanDistance(
        distance_km=round(sum(distance for distance, _ in routes), 3), provider=provider
    )


async def delete_plan(session: AsyncSession, plan_id: int) -> None:
    """Удаляет план или всю связанную пару baseline/cuOpt вместе с назначениями."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None:
        raise PlanNotFoundError(f"План №{plan_id} не найден")
    for compared_plan in await plans_repository.list_comparison_plans(session, plan):
        await plans_repository.delete_plan(session, compared_plan)
    await session.commit()


async def save_solution(
    session: AsyncSession,
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    *,
    run_type: PlanRunType = PlanRunType.OPTIMIZED,
    solver: str = SOLVER_NAME,
    comparison_id: UUID | None = None,
    solve_duration_ms: float | None = None,
) -> Plan:
    day = loaded.day
    plan = plans_repository.add_plan(
        session,
        run_type,
        day.plan_date,
        solver,
        comparison_id=comparison_id,
        solve_duration_ms=(
            Decimal(str(round(solve_duration_ms, 3))) if solve_duration_ms is not None else None
        ),
    )
    plan.input_snapshot = snapshot_inputs(loaded)
    await session.flush()

    # назначенные заявки — по маршрутам исполнителей, в порядке объезда
    assigned_request_indices: set[int] = set()
    for engineer_index, visits in solution.routes.items():
        engineer = loaded.engineers[engineer_index]
        for visit_order, visit in enumerate(visits, start=1):
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


async def list_plans(session: AsyncSession, plan_date: date | None) -> list[PlanSummary]:
    plans = await plans_repository.list_plans(session, plan_date)
    return await summarize_plans(session, plans)


async def summarize_plans(session: AsyncSession, plans: list[Plan]) -> list[PlanSummary]:
    plan_ids = [plan.id for plan in plans]
    counts = await plans_repository.count_assignments_by_plan(session, plan_ids)
    assigned_request_ids = await plans_repository.assigned_request_ids_by_plan(session, plan_ids)
    summaries = []
    for plan in plans:
        engineers_used, assigned, unassigned = counts.get(plan.id, (0, 0, 0))
        urgent_assigned_count = count_urgent_assignments(
            plan.input_snapshot, assigned_request_ids.get(plan.id, set())
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
                comparison_id=plan.comparison_id,
                solve_duration_ms=(
                    float(plan.solve_duration_ms) if plan.solve_duration_ms is not None else None
                ),
            )
        )
    return summaries


def count_urgent_assignments(snapshot: dict | None, assigned_request_ids: set[int]) -> int | None:
    """Срочные назначения считаются по снимку; старые снимки могли не хранить признак."""
    if not snapshot or "requests" not in snapshot:
        return None
    requests = snapshot["requests"]
    assigned = [requests.get(str(request_id)) for request_id in assigned_request_ids]
    if any(request is None or "is_urgent" not in request for request in assigned):
        return None
    return sum(bool(request["is_urgent"]) for request in assigned)


async def get_plan_detail(session: AsyncSession, plan_id: int) -> PlanDetail:
    """План с маршрутами: порядок визитов, пробег и линия каждого маршрута, неназначенные заявки."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None:
        raise PlanNotFoundError(f"План №{plan_id} не найден")

    stored_assignments = await plans_repository.list_plan_assignments(session, plan_id)
    assignments: list[AssignmentView] = list(stored_assignments)
    if plan.input_snapshot:
        assignments = [snapshot_assignment(a, plan.input_snapshot) for a in stored_assignments]
    assignments_by_engineer: dict[int, list[AssignmentView]] = defaultdict(list)
    unassigned = []
    for assignment in assignments:
        if assignment.engineer is None or assignment.engineer_id is None:
            unassigned.append(to_unassigned_request(assignment))
        else:
            assignments_by_engineer[assignment.engineer_id].append(assignment)

    engineer_assignments = sorted(assignments_by_engineer.values(), key=assigned_engineer_name)
    routes = await asyncio.gather(*(build_engineer_route(group) for group in engineer_assignments))

    summary = (await summarize_plans(session, [plan]))[0]
    compared_plans = [
        compared
        for compared in await plans_repository.list_comparison_plans(session, plan)
        if compared.id != plan.id
    ]
    comparison = (
        (await summarize_plans(session, [compared_plans[0]]))[0] if compared_plans else None
    )
    return PlanDetail(
        **summary.model_dump(exclude={"total_distance_km"}),
        total_distance_km=round(sum(route.distance_km for route in routes), 3),
        routes=list(routes),
        unassigned=unassigned,
        comparison=comparison,
    )


async def build_engineer_route(assignments: list[AssignmentView]) -> EngineerRoute:
    """Маршрут одного исполнителя: визиты по порядку, пробег и линия для карты.

    Пробег берётся из маршрутизатора (/route) по порядку визитов, а не из матрицы:
    матрица приближённая и занижает длинные плечи.
    """
    if not assignments:
        raise ValueError("маршрут не содержит назначений")
    if any(
        assignment.engineer is None
        or assignment.visit_order is None
        or assignment.planned_arrival_time is None
        for assignment in assignments
    ):
        raise ValueError("назначенный маршрут содержит неполные данные")

    ordered = sorted(assignments, key=assigned_visit_order)
    engineer = ordered[0].engineer
    if engineer is None:  # narrowing for static analysis; guarded above
        raise ValueError("у маршрута нет исполнителя")

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
    travel = await build_route(points, TransportKind(engineer.transport_id))

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
        visits=[to_plan_visit(assignment, engineer.name) for assignment in ordered],
    )


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


def to_plan_visit(assignment: AssignmentView, engineer_name: str) -> PlanVisit:
    if assignment.visit_order is None or assignment.planned_arrival_time is None:
        raise ValueError("назначение содержит неполные данные")
    request = assignment.request
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
        explanation=assignment_explanation(assignment, engineer_name),
    )


def assignment_explanation(assignment: AssignmentView, engineer_name: str) -> str:
    """Краткое объяснение назначения на языке диспетчера."""
    request = assignment.request
    transport = (
        "ограничений по транспорту у заявки нет"
        if request.transport_id is None
        else "транспорт соответствует требованию заявки"
    )
    return (
        f"Назначена исполнителю «{engineer_name}»: квалификация подходит, {transport}; "
        "работа начинается в окне заявки и заканчивается в пределах смены. "
        f"Позиция №{assignment.visit_order} выбрана при совместной оптимизации срочности, "
        "числа выполненных заявок, числа исполнителей и пробега."
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
    engineer = snapshot["engineers"].get(str(assignment.engineer_id))
    return SimpleNamespace(
        request=SimpleNamespace(**request),
        engineer=SimpleNamespace(**engineer) if engineer else None,
        engineer_id=assignment.engineer_id,
        visit_order=assignment.visit_order,
        planned_arrival_time=assignment.planned_arrival_time,
        unassigned_reason=assignment.unassigned_reason,
    )
