"""4.2 Каждая заявка назначена ровно одному инженеру — или не назначена никому.

Для каждой заявки:
    сумма «назначена инженеру» по всем подходящим инженерам + «не назначена» = 1
"""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_assignment_constraint(problem: MilpProblem, instance: ProblemInstance) -> None:
    for request_index in range(instance.n_requests):
        coefficients = []

        for engineer_index in range(instance.n_engineers):
            assigned_column = problem.assigned_column.get((engineer_index, request_index))
            if assigned_column is not None:
                coefficients.append((assigned_column, 1.0))

        coefficients.append((problem.unassigned_column[request_index], 1.0))
        problem.add_row(coefficients, "=", 1.0)
