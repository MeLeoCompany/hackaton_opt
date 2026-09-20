"""Проверка маршрутов ОТ по времени фактического выезда между заявками."""

import copy
import math

import httpx
import numpy as np

from src.core.config import settings
from src.core.errors import ExternalServiceError
from src.schemas.travel import Point, TransportKind
from src.services.planner import cuopt_solver
from src.services.planner.objective_policy import ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import ProblemInstance
from src.services.travel import build_route

TRANSIT_ID = TransportKind.PUBLIC_TRANSPORT.value


def node_points(loaded: LoadedDay) -> list[Point]:
    starts = loaded.start_points or [
        Point(latitude=float(e.start_latitude), longitude=float(e.start_longitude))
        for e in loaded.engineers
    ]
    return [
        *starts,
        *(Point(latitude=float(r.latitude), longitude=float(r.longitude)) for r in loaded.requests),
    ]


async def check_schedule(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
) -> tuple[cuopt_solver.DaySolution | None, dict[tuple[int, int], int]]:
    """Пересчитать начала работ; при нарушении вернуть замеры для следующей попытки."""
    instance = loaded.instance
    routes = dict(solution.routes)
    observations: dict[tuple[int, int], int] = {}
    valid = True
    for engineer_index, visits in solution.routes.items():
        engineer = instance.engineers[engineer_index]
        if engineer.transport_id != TRANSIT_ID or not visits:
            continue
        available = engineer.shift_start_min
        previous = instance.start_node(engineer_index)
        actual_visits = []
        for visit in visits:
            next_node = instance.request_node(visit.request_index)
            key = (previous, next_node, available)
            if key not in cache:
                try:
                    route = await build_route(
                        [points[previous], points[next_node]],
                        TransportKind.PUBLIC_TRANSPORT,
                        departure_time=loaded.day.from_minutes(available),
                        allow_fallback=False,
                    )
                except (httpx.HTTPError, KeyError, ValueError) as error:
                    raise ExternalServiceError(
                        f"R5 не смог проверить расписание плана: {error}"
                    ) from error
                cache[key] = math.ceil(route.duration_min - 1e-9)
            duration = cache[key]
            observations[previous, next_node] = max(
                observations.get((previous, next_node), 0), duration
            )
            request = instance.requests[visit.request_index]
            start = max(available + duration, request.window_start_min)
            if (
                start > request.window_end_min
                or start + request.duration_min > engineer.shift_end_min
            ):
                valid = False
            actual_visits.append(cuopt_solver.PlannedVisit(visit.request_index, start))
            available = start + request.duration_min
            previous = next_node
        routes[engineer_index] = actual_visits
    return (cuopt_solver.DaySolution(routes) if valid else None), observations


async def solve_day(
    loaded: LoadedDay, objective_order: tuple[ObjectiveCriterion, ...]
) -> cuopt_solver.DaySolution:
    """Уточнять только использованные плечи, не пересчитывая полную матрицу R5."""
    if TRANSIT_ID not in loaded.instance.travel_min:
        return await cuopt_solver.solve_day(loaded.instance, objective_order=objective_order)

    points = node_points(loaded)
    cache: dict[tuple[int, int, int], int] = {}
    instance: ProblemInstance = loaded.instance
    for attempt in range(settings.transit_plan_max_attempts):
        solution = await cuopt_solver.solve_day(instance, objective_order=objective_order)
        checked, observations = await check_schedule(loaded, solution, points, cache)
        if checked is not None:
            return checked
        if attempt + 1 == settings.transit_plan_max_attempts:
            break
        # Матрицу исходной задачи не меняем: её снимок и другие решатели используют сами.
        updated = instance.travel_min[TRANSIT_ID].copy()
        for (origin, destination), duration in observations.items():
            updated[origin, destination] = max(updated[origin, destination], duration)
        if np.array_equal(updated, instance.travel_min[TRANSIT_ID]):
            break
        instance = copy.copy(instance)
        instance.travel_min = {**instance.travel_min, TRANSIT_ID: updated}
    raise ExternalServiceError(
        "Не удалось построить план ОТ, который укладывается в окна заявок "
        "по фактическому расписанию R5"
    )
