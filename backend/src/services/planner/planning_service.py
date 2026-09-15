"""Планы: построение плана на день через cuOpt, список планов, план с маршрутами исполнителей."""

import asyncio
from collections import defaultdict
from datetime import date

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
    "Не поместилась в расписание: подходящие исполнители не успевают доехать и начать работу "
    "в окне заявки в пределах смены с учётом других заявок"
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


async def build_plan_for_day(session: AsyncSession, plan_date: date) -> PlanSummary:
    """Строит план на день через cuOpt и сохраняет его вместе с назначениями."""
    day = planner_loader.planning_day(plan_date)
    loaded = await planner_loader.load_day(session, day)
    if loaded.instance.n_requests == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет активных заявок"])
    if loaded.instance.n_engineers == 0:
        raise PlanDataError([f"На {plan_date:%d.%m.%Y} нет исполнителей со сменой"])

    solution = await cuopt_solver.solve_day(loaded.instance)

    plan = plans_repository.add_plan(session, PlanRunType.OPTIMIZED, plan_date, SOLVER_NAME)
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

    await session.commit()
    await session.refresh(plan)
    return (await summarize_plans(session, [plan]))[0]


def unassigned_reason(loaded: LoadedDay, request_index: int) -> str:
    """Почему заявка не назначена — понятным диспетчеру языком.

    Если заявку в принципе можно было отдать кому-то, значит не хватило времени. Иначе
    уточняем, чего не хватает: навыка или транспорта у исполнителей с этим навыком.
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
