from planner_test_helpers import (
    URGENT,
    engineer,
    make_instance,
    request,
    route_request_ids,
)

from src.services.planner.baseline_solver import solve_day


def test_assigns_requests_and_engineers_in_input_order():
    instance = make_instance(
        engineers=[engineer(10), engineer(20)],
        requests=[
            request(100, skill=1, window=("10:00", "10:30"), duration=60),
            request(200, skill=1, window=("10:00", "10:30"), duration=60),
        ],
        skills={10: {1}, 20: {1}},
        travel_min=0,
    )

    solution = solve_day(instance)

    assert route_request_ids(instance, solution, engineer_id=10) == [100]
    assert route_request_ids(instance, solution, engineer_id=20) == [200]


def test_does_not_reorder_urgent_request_ahead_of_earlier_regular_request():
    instance = make_instance(
        engineers=[engineer(1, shift=("10:00", "11:00"))],
        requests=[
            request(100, skill=1, window=("10:00", "11:00"), duration=60),
            request(200, skill=1, window=("10:00", "11:00"), duration=60, priority=URGENT),
        ],
        skills={1: {1}},
        travel_min=0,
    )

    solution = solve_day(instance)

    assert route_request_ids(instance, solution, engineer_id=1) == [100]


def test_appends_only_when_travel_service_window_and_shift_fit():
    instance = make_instance(
        engineers=[engineer(1, shift=("09:00", "13:00"))],
        requests=[
            request(100, skill=1, window=("09:30", "10:00"), duration=60),
            request(200, skill=1, window=("11:00", "11:30"), duration=60),
            request(300, skill=1, window=("12:00", "12:15"), duration=60),
        ],
        skills={1: {1}},
        travel_min=30,
    )

    solution = solve_day(instance)

    assert route_request_ids(instance, solution, engineer_id=1) == [100, 200]
    assert [visit.work_start_minute for visit in solution.routes[0]] == [570, 660]


def test_skips_incompatible_engineer_and_uses_next_one():
    instance = make_instance(
        engineers=[engineer(10), engineer(20)],
        requests=[request(100, skill=2, window=("10:00", "12:00"))],
        skills={10: {1}, 20: {2}},
    )

    solution = solve_day(instance)

    assert route_request_ids(instance, solution, engineer_id=10) == []
    assert route_request_ids(instance, solution, engineer_id=20) == [100]
