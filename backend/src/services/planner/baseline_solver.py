"""Простой контрольный алгоритм из ТЗ для сравнения с глобальной оптимизацией.

Заявки и исполнители рассматриваются в исходном порядке. Каждая заявка назначается
первому совместимому исполнителю, который может добавить её в конец своего маршрута.
Уже сделанные назначения не переставляются и не пересматриваются.
"""

from src.services.planner.cuopt_solver import DaySolution, PlannedVisit, validate_solution
from src.services.planner.planner_problem import ProblemInstance


def solve_day(instance: ProblemInstance) -> DaySolution:
    routes: dict[int, list[PlannedVisit]] = {}
    available_at: list[float] = [engineer.shift_start_min for engineer in instance.engineers]
    current_node = [instance.start_node(index) for index in range(instance.n_engineers)]

    for request_index, request in enumerate(instance.requests):
        for engineer_index, engineer in enumerate(instance.engineers):
            if not instance.compatible[request_index, engineer_index]:
                continue

            travel_minutes = float(
                instance.travel_min[engineer.transport_id][
                    current_node[engineer_index], instance.request_node(request_index)
                ]
            )
            work_start = max(
                available_at[engineer_index] + travel_minutes,
                request.window_start_min,
            )
            if (
                work_start > request.window_end_min
                or work_start + request.duration_min > engineer.shift_end_min
            ):
                continue

            routes.setdefault(engineer_index, []).append(
                PlannedVisit(request_index=request_index, work_start_minute=work_start)
            )
            available_at[engineer_index] = work_start + request.duration_min
            current_node[engineer_index] = instance.request_node(request_index)
            break

    solution = DaySolution(routes=routes)
    validate_solution(instance, solution)
    return solution
