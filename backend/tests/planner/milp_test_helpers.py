"""Вспомогательные функции для тестов планировщика.

Задачи собираются вручную с простыми матрицами (одинаковое время и расстояние между
любыми двумя точками), чтобы правильный ответ можно было посчитать в уме.
"""

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from src.services.planner import EngineerSpec, ProblemInstance, RequestSpec, build_compatibility

CAR = 1
WALK = 2

REGULAR = 1.0
URGENT = 100.0


def hhmm(clock_time: str) -> int:
    """'10:00' -> 600 минут от начала суток."""
    hours, minutes = clock_time.split(":")
    return int(hours) * 60 + int(minutes)


def engineer(engineer_id, transport=CAR, shift=("08:00", "18:00")):
    return EngineerSpec(engineer_id, f"инженер {engineer_id}", transport, hhmm(shift[0]), hhmm(shift[1]))


def request(request_id, skill, window, duration=60, transport=None, priority=REGULAR):
    return RequestSpec(request_id, duration, hhmm(window[0]), hhmm(window[1]), skill, transport, priority)


def make_instance(engineers, requests, skills, travel_min=10, distance_km=5.0):
    """Собирает задачу, где между любыми двумя разными точками travel_min минут и distance_km км.

    skills — навыки по engineer_id, например {1: {1, 2}, 2: {3}}.
    """
    node_count = len(engineers) + len(requests) + 1

    travel = np.full((node_count, node_count), travel_min, dtype=np.int32)
    np.fill_diagonal(travel, 0)
    distance = np.full((node_count, node_count), distance_km)
    np.fill_diagonal(distance, 0.0)

    transports = {each.transport_id for each in engineers}
    instance = ProblemInstance(
        engineers=engineers,
        requests=requests,
        distance_km={transport: distance for transport in transports},
        travel_min={transport: travel for transport in transports},
    )
    build_compatibility(instance, skills)
    return instance


def solve(problem):
    """Решает задачу через HiGHS и возвращает значения всех переменных."""
    row_lower_bounds = np.where(problem.signs == "<=", -np.inf, problem.b)
    result = milp(
        c=problem.costs,
        constraints=[LinearConstraint(problem.A, row_lower_bounds, problem.b)],
        integrality=problem.is_integer,
        bounds=Bounds(problem.lower_bounds, problem.upper_bounds),
        options={"time_limit": 30},
    )
    assert result.x is not None, f"решатель не нашёл решение: {result.message}"
    return result.x


def read_plan(problem, instance, values):
    """Переводит значения переменных в понятный план.

    routes     — {engineer_id: [(начало работ в минутах, request_id), ...]} по времени
    unassigned — [request_id, ...]
    """
    routes = {}
    for (engineer_index, request_index), assigned_column in problem.assigned_column.items():
        if values[assigned_column] > 0.5:
            work_start = round(values[problem.work_start_column[request_index]])
            engineer_id = instance.engineers[engineer_index].engineer_id
            request_id = instance.requests[request_index].request_id
            routes.setdefault(engineer_id, []).append((work_start, request_id))
    for visits in routes.values():
        visits.sort()

    unassigned = [
        instance.requests[request_index].request_id
        for request_index, unassigned_column in problem.unassigned_column.items()
        if values[unassigned_column] > 0.5
    ]
    return routes, unassigned
