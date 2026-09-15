"""Ограничения 4.2-4.5: какие строки каждое из них добавляет в A.

Каждый тест собирает переменные и ровно одно ограничение — удобно поставить брейкпоинт
внутри add_*_constraint и посмотреть на problem.A.toarray().
"""

from milp_test_helpers import engineer, make_instance, request

from src.services.planner.constraints.assignment_constraint import add_assignment_constraint
from src.services.planner.constraints.flow_constraint import add_flow_constraint
from src.services.planner.constraints.time_constraint import add_time_constraint
from src.services.planner.constraints.usage_constraint import add_usage_constraint
from src.services.planner.milp_problem import MilpProblem
from src.services.planner.milp_variables import add_variables


def build_with(instance, add_constraint):
    problem = MilpProblem()
    add_variables(problem, instance)
    add_constraint(problem, instance)
    problem.finalize()
    return problem


def row_coefficients(problem, row_number):
    """Строка A в виде {номер столбца: коэффициент}, без нулей."""
    dense_row = problem.A.getrow(row_number).toarray().ravel()
    return {column: dense_row[column] for column in dense_row.nonzero()[0]}


def same_window_instance():
    """Две заявки в одном окне 10:00-12:00 — порядок между ними действительно важен."""
    return make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("10:00", "12:00")),
        ],
        skills={1: {1}},
    )


def test_assignment_one_row_per_request(basic_instance):
    problem = build_with(basic_instance, add_assignment_constraint)

    assert problem.n_rows == basic_instance.n_requests
    assert all(sign == "=" for sign in problem.signs)
    assert all(right_side == 1.0 for right_side in problem.b)


def test_assignment_row_contains_candidates_and_unassigned(basic_instance):
    problem = build_with(basic_instance, add_assignment_constraint)

    # заявку 10 (номер 0) можно назначить только первому инженеру (номер 0)
    assert row_coefficients(problem, 0) == {
        problem.assigned_column[(0, 0)]: 1.0,
        problem.unassigned_column[0]: 1.0,
    }


def test_flow_row_count(basic_instance):
    problem = build_with(basic_instance, add_flow_constraint)

    # по 2 строки на каждую пару «инженер-заявка» (въезд, выезд) + по 2 на инженера (старт, финиш)
    expected_rows = 2 * len(problem.assigned_column) + 2 * basic_instance.n_engineers
    assert problem.n_rows == expected_rows
    assert all(sign == "=" for sign in problem.signs)


def test_usage_links_assignment_to_engineer(basic_instance):
    problem = build_with(basic_instance, add_usage_constraint)

    assert problem.n_rows == len(problem.assigned_column)
    assert row_coefficients(problem, 0) == {
        problem.assigned_column[(0, 0)]: 1.0,
        problem.engineer_used_column[0]: -1.0,
    }
    assert problem.signs[0] == "<=" and problem.b[0] == 0.0


def test_time_row_skipped_when_it_can_never_bind(basic_instance):
    problem = build_with(basic_instance, add_time_constraint)

    # окна 10-12 и 15-17 не конфликтуют: даже начав первую в 12:00, во вторую приедешь
    # в 13:10, раньше открытия окна. Строка ничего не отсекает — её и не добавляем.
    assert problem.n_rows == 0


def test_time_rows_are_inequalities():
    problem = build_with(same_window_instance(), add_time_constraint)

    assert problem.n_rows > 0
    assert all(sign == "<=" for sign in problem.signs)


def test_time_row_between_requests():
    instance = same_window_instance()
    problem = build_with(instance, add_time_constraint)
    drive_column = problem.drive_column[(0, instance.request_node(0), instance.request_node(1))]

    # начало_10 - начало_11 + big_m · переезд <= big_m - (работа 60 + дорога 10)
    # big_m = конец окна 10 (12:00) + 70 - начало окна 11 (10:00) = 190
    rows_with_drive = [
        row_number for row_number in range(problem.n_rows)
        if drive_column in row_coefficients(problem, row_number)
    ]
    assert len(rows_with_drive) == 1
    row_number = rows_with_drive[0]
    assert row_coefficients(problem, row_number) == {
        problem.work_start_column[0]: 1.0,
        problem.work_start_column[1]: -1.0,
        drive_column: 190.0,
    }
    assert problem.b[row_number] == 190 - 70
