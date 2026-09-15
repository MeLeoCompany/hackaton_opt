"""4.5 Если инженеру назначена хотя бы одна заявка — он считается задействованным.

Для каждой пары (инженер, заявка):
    «заявка назначена инженеру» - «инженер задействован» <= 0

Именно за «инженер задействован» целевая функция берёт плату — так решатель старается
обойтись меньшим числом людей.
"""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_usage_constraint(problem: MilpProblem, instance: ProblemInstance) -> None:
    for (engineer_index, _request_index), assigned_column in problem.assigned_column.items():
        engineer_used_column = problem.engineer_used_column[engineer_index]
        problem.add_row([(assigned_column, 1.0), (engineer_used_column, -1.0)], "<=", 0.0)
