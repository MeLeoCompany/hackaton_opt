"""Сборка задачи по шагам: каждый шаг дописывает свою часть в MilpProblem."""

import time

from src.services.planner.constraints.assignment_constraint import add_assignment_constraint
from src.services.planner.constraints.flow_constraint import add_flow_constraint
from src.services.planner.constraints.time_constraint import add_time_constraint
from src.services.planner.constraints.usage_constraint import add_usage_constraint
from src.services.planner.milp_objective import add_objective
from src.services.planner.milp_problem import MilpProblem
from src.services.planner.milp_variables import add_variables
from src.services.planner.planner_problem import ProblemInstance


def build_milp(
    instance: ProblemInstance,
    unassigned_penalty: float = 1e6,
    engineer_cost: float = 1e3,
    cost_per_km: float = 1.0,
) -> MilpProblem:
    """Собирает из исходных данных готовую матричную задачу и замеряет время каждого шага."""
    problem = MilpProblem()

    def run_step(step_name, add_part, *extra_arguments):
        started = time.perf_counter()
        add_part(problem, instance, *extra_arguments)
        problem.timings[step_name] = time.perf_counter() - started

    run_step("1. переменные", add_variables)
    run_step("2. целевая функция", add_objective, unassigned_penalty, engineer_cost, cost_per_km)
    run_step("4.2 назначение", add_assignment_constraint)
    run_step("4.3 поток", add_flow_constraint)
    run_step("4.4 время", add_time_constraint)
    run_step("4.5 занятость", add_usage_constraint)

    started = time.perf_counter()
    problem.finalize()
    problem.timings["5. сборка A"] = time.perf_counter() - started

    return problem
