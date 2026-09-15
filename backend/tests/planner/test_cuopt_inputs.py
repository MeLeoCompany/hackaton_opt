"""Что уходит в cuOpt и как разбирается его ответ — без видеокарты и без самого пакета cuopt."""

import numpy as np
from planner_test_helpers import CAR, URGENT, WALK, engineer, hhmm, make_instance, request, solve

from src.services.planner.cuopt_solver import (
    build_solver_inputs,
    parse_route_records,
    schedulable_request_indices,
)


def sample_instance():
    """Два исполнителя, три заявки; аварийную (навык 3) не умеет никто."""
    return make_instance(
        engineers=[
            engineer(1, transport=CAR),
            engineer(2, transport=WALK, shift=("09:00", "18:00")),
        ],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=2, window=("15:00", "17:00"), priority=URGENT),
            request(12, skill=3, window=("10:00", "12:00")),
        ],
        skills={1: {1}, 2: {1, 2}},
    )


def test_request_nobody_can_do_is_not_sent():
    assert schedulable_request_indices(sample_instance()) == [0, 1]


def test_day_without_schedulable_requests_is_not_sent_to_solver():
    # решатель даже не вызывается, поэтому тест работает и без cuopt
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[request(10, skill=3, window=("10:00", "12:00"))],
        skills={1: {1}},
    )

    assert solve(instance).routes == {}


def test_engineers_become_vehicles():
    inputs = build_solver_inputs(sample_instance(), [0, 1])

    assert inputs.vehicle_locations.tolist() == [0, 1]
    assert inputs.vehicle_types.tolist() == [CAR, WALK]
    assert inputs.vehicle_types.dtype == np.uint8
    assert inputs.vehicle_shift_start.tolist() == [hhmm("08:00"), hhmm("09:00")]
    assert inputs.vehicle_shift_end.tolist() == [hhmm("18:00"), hhmm("18:00")]


def test_requests_become_orders():
    inputs = build_solver_inputs(sample_instance(), [0, 1])

    assert inputs.order_locations.tolist() == [2, 3]  # точки заявок идут после стартов двух исполнителей
    assert inputs.order_window_start.tolist() == [hhmm("10:00"), hhmm("15:00")]
    assert inputs.order_window_end.tolist() == [hhmm("12:00"), hhmm("17:00")]
    assert inputs.order_service_minutes.tolist() == [60, 60]
    assert inputs.order_prizes[1] == 100 * inputs.order_prizes[0]  # срочная дороже
    assert [allowed.tolist() for allowed in inputs.order_allowed_vehicles] == [
        [0, 1],  # навык 1 есть у обоих
        [1],  # навык 2 — только у второго
    ]


def test_matrices_per_transport():
    instance = sample_instance()
    inputs = build_solver_inputs(instance, [0, 1])
    point_count = instance.n_engineers + instance.n_requests

    assert inputs.location_count == point_count
    assert set(inputs.cost_matrices) == {CAR, WALK}
    assert set(inputs.travel_time_matrices) == {CAR, WALK}
    assert inputs.cost_matrices[CAR].shape == (point_count, point_count)
    assert inputs.travel_time_matrices[WALK].dtype == np.float32


def test_route_table_becomes_ordered_visits():
    route_records = [
        {"vehicle_id": 1, "route": 0, "arrival_stamp": 540.0, "location": 1, "type": "Depot"},
        {"vehicle_id": 1, "route": 1, "arrival_stamp": 900.0, "location": 3, "type": "Delivery"},
        {"vehicle_id": 1, "route": 0, "arrival_stamp": 970.0, "location": 2, "type": "Delivery"},
    ]
    solution = parse_route_records(route_records, task_request_indices=[0, 1])

    assert list(solution.routes) == [1]
    visits = [(visit.request_index, visit.work_start_minute) for visit in solution.routes[1]]
    assert visits == [(1, 900.0), (0, 970.0)]
