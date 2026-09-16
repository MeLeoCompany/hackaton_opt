"""Построение плана дня через cuOpt, сохранение и просмотр планов."""

import asyncio
from collections import defaultdict
from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, NotFoundError
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
from src.schemas.travel import Point, TransportKind
from src.services.planner import cuopt_solver, planner_loader
from src.services.planner.planner_loader import LoadedDay
from src.services.travel import build_route

SOLVER_NAME = "cuopt"

SCHEDULE_REASON = (
    "Не включена в найденный план: при расчёте учитывались время дороги, "
    "окна заявок, длительность работ, смены и приоритеты других заявок"
)


class PlanNotFoundError(NotFoundError):
    """Плана с таким номером нет."""


class PlanDataError(DataError):
    """План на этот день построить нельзя."""


async def list_planning_days(session: AsyncSession) -> list[PlanningDayOption]:
    """Дни, на которые есть активные заявки (по московской дате начала окна)."""
    requests = await requests_repository.list_active_requests(session)
    request_count_by_day: dict[date, int] = defaultdict(int)
    for request in requests:
        request_count_by_day[planner_loader.local_date_of(request.window_start)] += 1
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
    solution = await cuopt_solver.solve_day(loaded.instance)
    plan = await save_solution(session, loaded, solution)
    await session.commit()
    return (await summarize_plans(session, [plan]))[0]


async def save_solution(
    session: AsyncSession, loaded: LoadedDay, solution: cuopt_solver.DaySolution
) -> Plan:
    day = loaded.day
    plan = plans_repository.add_plan(session, PlanRunType.OPTIMIZED, day.plan_date, SOLVER_NAME)
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

    Для заявок, которые кому-то подходят, причина в расписании. Иначе уточняем,
    чего именно не хватило: навыка или транспорта.
    """
    if loaded.instance.compatible[request_index].any():
        return SCHEDULE_REASON

    request = loaded.requests[request_index]
    skill_name = loaded.skill_names.get(request.skill_id, f"№{request.skill_id}")
    engineers_with_skill = [
        engineer for engineer in loaded.engineers if request.skill_id in {skill.id for skill in engineer.skills}
    ]
    if not engineers_with_skill:
        return f"На этот день нет исполнителя с навыком «{skill_name}»"

    transport_name = loaded.transport_names.get(request.transport_id, f"№{request.transport_id}")
    return f"Исполнители с навыком «{skill_name}» есть, но ни у одного нет транспорта «{transport_name}»"


async def list_plans(session: AsyncSession, plan_date: date | None) -> list[PlanSummary]:
    plans = await plans_repository.list_plans(session, plan_date)
    return await summarize_plans(session, plans)


async def summarize_plans(session: AsyncSession, plans: list[Plan]) -> list[PlanSummary]:
    counts = await plans_repository.count_assignments_by_plan(session, [plan.id for plan in plans])
    summaries = []
    for plan in plans:
        engineers_used, assigned, unassigned = counts.get(plan.id, (0, 0, 0))
        summaries.append(
            PlanSummary(
                id=plan.id,
                run_type=plan.run_type.value,
                plan_date=plan.plan_date,
                solver=plan.solver,
                created_at=plan.created_at,
                engineers_used=engineers_used,
                assigned_count=assigned,
                unassigned_count=unassigned,
            )
        )
    return summaries


async def get_plan_detail(session: AsyncSession, plan_id: int) -> PlanDetail:
    """План с маршрутами: порядок визитов, пробег и линия каждого маршрута, неназначенные заявки."""
    plan = await plans_repository.get_plan(session, plan_id)
    if plan is None:
        raise PlanNotFoundError(f"План №{plan_id} не найден")

    assignments = await plans_repository.list_plan_assignments(session, plan_id)
    if plan.input_snapshot:
        assignments = [snapshot_assignment(a, plan.input_snapshot) for a in assignments]
    assignments_by_engineer: dict[int, list[Assignment]] = defaultdict(list)
    unassigned = []
    for assignment in assignments:
        if assignment.engineer is None:
            unassigned.append(to_unassigned_request(assignment))
        else:
            assignments_by_engineer[assignment.engineer_id].append(assignment)

    engineer_assignments = sorted(assignments_by_engineer.values(), key=lambda group: group[0].engineer.name)
    routes = await asyncio.gather(*(build_engineer_route(group) for group in engineer_assignments))

    summary = (await summarize_plans(session, [plan]))[0]
    return PlanDetail(
        **summary.model_dump(),
        total_distance_km=round(sum(route.distance_km for route in routes), 3),
        routes=list(routes),
        unassigned=unassigned,
    )


async def build_engineer_route(assignments: list[Assignment]) -> EngineerRoute:
    """Маршрут одного исполнителя: визиты по порядку, пробег и линия для карты.

    Пробег берётся из маршрутизатора (/route) по порядку визитов, а не из матрицы:
    матрица приближённая и занижает длинные плечи.
    """
    ordered = sorted(assignments, key=lambda assignment: assignment.visit_order)
    engineer = ordered[0].engineer

    points = [Point(latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude))]
    points += [
        Point(latitude=float(assignment.request.latitude), longitude=float(assignment.request.longitude))
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
        visits=[to_plan_visit(assignment) for assignment in ordered],
    )


def to_plan_visit(assignment: Assignment) -> PlanVisit:
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
    )


def to_unassigned_request(assignment: Assignment) -> UnassignedRequest:
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
    requests = {str(r.id): {
        "id": r.id, "address": r.address, "latitude": float(r.latitude),
        "longitude": float(r.longitude), "window_start": r.window_start.isoformat(),
        "window_end": r.window_end.isoformat(), "duration_minutes": r.duration_minutes,
        "priority_id": r.priority_id, "skill_id": r.skill_id, "transport_id": r.transport_id,
    } for r in loaded.requests}
    engineers = {str(e.id): {
        "id": e.id, "name": e.name, "start_latitude": float(e.start_latitude),
        "start_longitude": float(e.start_longitude), "transport_id": e.transport_id,
        "shift_start": e.shift_start.isoformat(), "shift_end": e.shift_end.isoformat(),
        "skill_ids": [skill.id for skill in e.skills],
    } for e in loaded.engineers}
    return {"requests": requests, "engineers": engineers,
            "request_order": [r.id for r in loaded.requests],
            "engineer_order": [e.id for e in loaded.engineers]}


def snapshot_assignment(assignment: Assignment, snapshot: dict) -> SimpleNamespace:
    request = dict(snapshot["requests"][str(assignment.request_id)])
    for key in ("window_start", "window_end"):
        request[key] = datetime.fromisoformat(request[key])
    engineer = snapshot["engineers"].get(str(assignment.engineer_id))
    return SimpleNamespace(
        request=SimpleNamespace(**request),
        engineer=SimpleNamespace(**engineer) if engineer else None,
        engineer_id=assignment.engineer_id, visit_order=assignment.visit_order,
        planned_arrival_time=assignment.planned_arrival_time,
        unassigned_reason=assignment.unassigned_reason,
    )
