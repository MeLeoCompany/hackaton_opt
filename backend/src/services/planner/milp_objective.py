"""Шаг 2. Целевая функция — что решатель старается сделать как можно меньше.

    unassigned_penalty · (неназначенные заявки, срочные с весом)
  + engineer_cost      · (задействованные инженеры)
  + cost_per_km        · (суммарный пробег)

Штраф за неназначенную заявку намного больше цены инженера, а цена инженера намного
больше цены километра. Поэтому решатель сначала назначает как можно больше заявок,
потом обходится как можно меньшим числом инженеров, и только потом сокращает пробег.
"""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_objective(
    problem: MilpProblem,
    instance: ProblemInstance,
    unassigned_penalty: float,
    engineer_cost: float,
    cost_per_km: float,
) -> None:
    for (engineer_index, from_node, to_node), drive_column in problem.drive_column.items():
        kilometers = instance.distance_for(engineer_index, from_node, to_node)
        problem.costs[drive_column] = cost_per_km * kilometers

    for engineer_used_column in problem.engineer_used_column.values():
        problem.costs[engineer_used_column] = engineer_cost

    for request_index, unassigned_column in problem.unassigned_column.items():
        priority = instance.requests[request_index].priority_weight
        problem.costs[unassigned_column] = unassigned_penalty * priority
