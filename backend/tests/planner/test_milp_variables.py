"""Шаг 1: какие переменные заводятся и с какими границами."""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.milp_variables import add_variables


def build_variables(instance):
    problem = MilpProblem()
    add_variables(problem, instance)
    return problem


def test_drive_forward_in_time_exists(basic_instance):
    problem = build_variables(basic_instance)
    morning_node = basic_instance.request_node(0)  # заявка 10, окно 10:00-12:00
    afternoon_node = basic_instance.request_node(1)  # заявка 11, окно 15:00-17:00

    assert (0, morning_node, afternoon_node) in problem.drive_column


def test_drive_backward_in_time_is_pruned(basic_instance):
    problem = build_variables(basic_instance)
    morning_node = basic_instance.request_node(0)
    afternoon_node = basic_instance.request_node(1)

    # из 15:00 в окно, закрывшееся в 12:00, не попасть — переменной быть не должно
    assert (0, afternoon_node, morning_node) not in problem.drive_column


def test_incompatible_pair_has_no_assignment(basic_instance):
    problem = build_variables(basic_instance)

    # у второго инженера (номер 1) нет навыка 1 — заявки 10 и 11 ему не назначаются
    assert (1, 0) not in problem.assigned_column
    assert (1, 1) not in problem.assigned_column
    assert (1, 2) in problem.assigned_column


def test_every_assignable_request_can_finish_route(basic_instance):
    problem = build_variables(basic_instance)

    for engineer_index, request_index in problem.assigned_column:
        drive = (engineer_index, basic_instance.request_node(request_index), basic_instance.end_node)
        assert drive in problem.drive_column


def test_work_start_bounded_by_window(basic_instance):
    problem = build_variables(basic_instance)
    column = problem.work_start_column[0]

    assert problem.lower_bounds[column] == 600  # 10:00
    assert problem.upper_bounds[column] == 720  # 12:00
    assert problem.is_integer[column] == 0


def test_decision_variables_are_binary(basic_instance):
    problem = build_variables(basic_instance)
    decision_columns = [
        *problem.drive_column.values(),
        *problem.assigned_column.values(),
        *problem.engineer_used_column.values(),
        *problem.unassigned_column.values(),
    ]

    for column in decision_columns:
        bounds_and_type = (problem.lower_bounds[column], problem.upper_bounds[column], problem.is_integer[column])
        assert bounds_and_type == (0.0, 1.0, 1)
