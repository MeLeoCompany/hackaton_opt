"""Базовый алгоритм ТЗ 2.3: входной порядок, первый подходящий инженер, добавление в конец."""

from src.services.planner.cuopt_solver import DaySolution, PlannedVisit, validate_solution
from src.services.planner.planner_problem import ProblemInstance


def solve_day(instance: ProblemInstance) -> DaySolution:
    solution = DaySolution()
    positions = [instance.start_node(i) for i in range(instance.n_engineers)]
    free_at = [engineer.shift_start_min for engineer in instance.engineers]
    for request_index, request in enumerate(instance.requests):
        destination = instance.request_node(request_index)
        for engineer_index, engineer in enumerate(instance.engineers):
            if not instance.compatible[request_index, engineer_index]:
                continue
            travel = instance.travel_min[engineer.transport_id][positions[engineer_index], destination]
            start = max(free_at[engineer_index] + travel, request.window_start_min)
            end = start + request.duration_min
            if start > request.window_end_min or end > engineer.shift_end_min:
                continue
            solution.routes.setdefault(engineer_index, []).append(PlannedVisit(request_index, float(start)))
            positions[engineer_index] = destination
            free_at[engineer_index] = end
            break
    validate_solution(instance, solution)
    return solution
