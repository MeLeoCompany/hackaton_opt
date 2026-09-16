from dataclasses import replace

from planner_test_helpers import (
    CAR, WALK, URGENT, constraint_violations, engineer, make_instance, request, route_request_ids,
)
from src.services.planner.baseline_solver import solve_day


def test_first_input_engineer_wins_even_if_id_is_larger_and_route_longer():
    skills = {90: {1}, 1: {1}}
    problem = make_instance([engineer(90), engineer(1)],
                            [request(10, 1, ('10:00', '12:00'))], skills)
    problem.distance_km[CAR][0, 2] = 100
    result = solve_day(problem)
    assert route_request_ids(problem, result, 90) == [10]
    assert constraint_violations(problem, skills, result) == []


def test_arrival_order_is_not_sorted_by_window_id_or_priority():
    skills = {1: {1}, 2: {1}}
    problem = make_instance([engineer(1), engineer(2)], [
        request(90, 1, ('15:00', '16:00')),
        request(1, 1, ('10:00', '11:00'), priority=URGENT),
    ], skills)
    result = solve_day(problem)
    assert route_request_ids(problem, result, 1) == [90]
    assert route_request_ids(problem, result, 2) == [1]
    assert constraint_violations(problem, skills, result) == []


def test_waiting_travel_shift_skill_transport_and_unassigned():
    skills = {1: {1}, 2: {1, 2}}
    problem = make_instance([engineer(1, transport=WALK), engineer(2)], [
        request(1, 2, ('10:00', '11:00'), transport=CAR),
        request(2, 1, ('10:00', '11:00'), transport=CAR),
        request(3, 3, ('10:00', '11:00')),
        request(4, 1, ('17:30', '18:00'), duration=60),
        request(5, 1, ('14:00', '15:00')),
    ], skills)
    result = solve_day(problem)
    assert route_request_ids(problem, result, 2) == [1]
    assert route_request_ids(problem, result, 1) == [5]
    assert constraint_violations(problem, skills, result) == []


def test_work_may_end_at_shift_end_without_return_trip():
    problem = make_instance([engineer(1)], [request(1, 1, ('17:00', '17:01'))], {1: {1}})
    assert route_request_ids(problem, solve_day(problem), 1) == [1]


def test_unreachable_and_empty_windows_are_dropped():
    problem = make_instance([engineer(1)], [request(1, 1, ('10:00', '11:00'))], {1: {1}}, travel_min=100000)
    assert solve_day(problem).routes == {}
    problem.requests[0] = replace(problem.requests[0], window_start_min=601, window_end_min=600)
    assert solve_day(problem).routes == {}


def test_no_engineers_or_requests():
    assert solve_day(make_instance([], [], {})).routes == {}
