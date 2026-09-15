"""4.3 Маршрут инженера — одна непрерывная цепочка переездов.

Для каждой заявки, которую можно отдать инженеру:
    сколько раз он в неё въехал  = назначена ли она ему (0 или 1)
    сколько раз он из неё выехал = назначена ли она ему (0 или 1)

Для каждого инженера:
    сколько раз выехал со старта  = задействован ли он (0 или 1)
    сколько раз приехал на финиш  = задействован ли он (0 или 1)

Финиш фиктивный и ничего не стоит. Без него у последней заявки маршрута не было бы
выезда, и равенство «выехал = назначена» сделало бы задачу неразрешимой.
"""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_flow_constraint(problem: MilpProblem, instance: ProblemInstance) -> None:
    for engineer_index in range(instance.n_engineers):
        for request_index in range(instance.n_requests):
            assigned_column = problem.assigned_column.get((engineer_index, request_index))
            if assigned_column is None:
                continue
            request_node = instance.request_node(request_index)

            # въехал в заявку = заявка назначена
            drives_in = problem.drives_into[(engineer_index, request_node)]
            problem.add_row(
                [(column, 1.0) for column in drives_in] + [(assigned_column, -1.0)], "=", 0.0
            )

            # выехал из заявки = заявка назначена
            drives_out = problem.drives_out_of[(engineer_index, request_node)]
            problem.add_row(
                [(column, 1.0) for column in drives_out] + [(assigned_column, -1.0)], "=", 0.0
            )

        engineer_used_column = problem.engineer_used_column[engineer_index]

        # выехал со старта = инженер задействован
        drives_from_start = problem.drives_out_of[(engineer_index, instance.start_node(engineer_index))]
        problem.add_row(
            [(column, 1.0) for column in drives_from_start] + [(engineer_used_column, -1.0)], "=", 0.0
        )

        # приехал на финиш = инженер задействован
        drives_to_finish = problem.drives_into[(engineer_index, instance.end_node)]
        problem.add_row(
            [(column, 1.0) for column in drives_to_finish] + [(engineer_used_column, -1.0)], "=", 0.0
        )
