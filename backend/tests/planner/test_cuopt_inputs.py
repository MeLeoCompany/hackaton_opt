"""Что уходит в cuOpt и как разбирается его ответ — без видеокарты и без самого пакета cuopt."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from planner_test_helpers import (
    CAR,
    CONNECTION,
    EMERGENCY,
    REGULAR,
    URGENT,
    WALK,
    engineer,
    hhmm,
    make_instance,
    request,
    solve,
)

from src.schemas.system import SolverParams
from src.services.planner.cuopt_solver import (
    build_objective_policy,
    build_solver_inputs,
    parse_route_records,
    schedulable_request_indices,
)
from src.services.planner.objective_policy import ObjectiveCriterion
from src.services.planner.planner_problem import (
    RANK_EMERGENCY,
    RANK_HIGH,
    RANK_MOVED_HIGH,
    RANK_MOVED_NORMAL,
    RANK_NORMAL,
    RANK_PROMISED,
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

    assert inputs.order_locations.tolist() == [
        2,
        3,
    ]  # точки заявок идут после стартов двух исполнителей
    assert inputs.order_window_start.tolist() == [hhmm("10:00"), hhmm("15:00")]
    assert inputs.order_window_end.tolist() == [hhmm("12:00"), hhmm("17:00")]
    assert inputs.order_service_minutes.tolist() == [60, 60]
    assert inputs.order_prizes[0] == inputs.objective.regular_reward
    assert inputs.order_prizes[1] == inputs.objective.reward_for(RANK_EMERGENCY)
    assert inputs.order_prizes[1] > inputs.order_prizes[0]
    assert [allowed.tolist() for allowed in inputs.order_allowed_vehicles] == [
        [0, 1],  # навык 1 есть у обоих
        [1],  # навык 2 — только у второго
    ]


def test_matrices_per_transport():
    instance = sample_instance()
    inputs = build_solver_inputs(instance, [0, 1])
    point_count = instance.n_engineers + 2

    assert inputs.location_count == point_count
    assert set(inputs.cost_matrices) == {CAR, WALK}
    assert set(inputs.travel_time_matrices) == {CAR, WALK}
    assert inputs.cost_matrices[CAR].shape == (point_count, point_count)
    assert inputs.travel_time_matrices[WALK].dtype == np.float32


def test_solver_matrices_exclude_requests_not_sent_to_cuopt():
    instance = sample_instance()
    inputs = build_solver_inputs(instance, [0, 1])

    assert inputs.location_count == 4
    assert inputs.order_locations.tolist() == [2, 3]
    assert inputs.cost_matrices[CAR].shape == (4, 4)


@pytest.mark.parametrize(
    ("matrix_kind", "invalid", "message"),
    [
        ("travel_min", np.nan, "недопустимые значения"),
        ("travel_min", -1, "недопустимые значения"),
        ("distance_km", np.inf, "недопустимые значения"),
        ("distance_km", 1e40, "float32"),
    ],
)
def test_invalid_matrices_are_rejected_before_cuopt(matrix_kind, invalid, message):
    instance = sample_instance()
    if np.isnan(invalid):
        getattr(instance, matrix_kind)[CAR] = getattr(instance, matrix_kind)[CAR].astype(float)
    getattr(instance, matrix_kind)[CAR][0, 1] = invalid

    with pytest.raises(ValueError, match=message):
        build_solver_inputs(instance, [0, 1])


def test_missing_transport_matrix_is_rejected_before_cuopt():
    instance = sample_instance()
    del instance.travel_min[WALK]

    with pytest.raises(ValueError, match="неверный размер"):
        build_solver_inputs(instance, [0, 1])


def test_compact_order_locations_keep_original_request_mapping():
    instance = sample_instance()
    inputs = build_solver_inputs(instance, [0, 2])
    records = [
        {"truck_id": 0, "route": 1, "arrival_stamp": 600.0, "type": "Delivery"},
    ]

    solution = parse_route_records(records, task_request_indices=[0, 2])

    assert inputs.order_locations.tolist() == [2, 3]
    assert solution.routes[0][0].request_index == 2


def test_time_limit_grows_with_problem_size_and_is_capped():
    """Время поиска задаёт оператор в параметрах расчёта: это и есть «точность»."""
    params = SolverParams(time_limit_seconds=2.0, max_time_limit_seconds=20.0)
    inputs = build_solver_inputs(sample_instance(), [0, 1], params=params)

    assert inputs.time_limit_seconds == 2.0  # маленькой задаче хватает базового времени
    inputs.location_count = 50
    assert inputs.time_limit_seconds == 6.0  # 30 точек сверх бесплатных по 0.2 с
    inputs.location_count = 1_000
    assert inputs.time_limit_seconds == 20.0  # выше максимума не поднимаемся


def test_dynamic_objective_has_strict_priority_levels():
    instance = sample_instance()
    inputs = build_solver_inputs(instance, [0, 1], distance_weight=1.0)
    objective = inputs.objective

    lower_than_request = instance.n_engineers * objective.vehicle_cost + objective.distance_weight
    assert objective.vehicle_cost > objective.distance_weight
    assert objective.regular_reward > lower_than_request
    assert objective.reward_for(RANK_EMERGENCY) > objective.regular_reward + lower_than_request


def test_dispatcher_can_save_crews_before_taking_more_requests():
    """«Меньше бригад» сразу после приоритетов: обычная заявка бригаду уже не оправдывает."""
    instance = sample_instance()
    order = (
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.ENGINEERS_USED,
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
    )

    tasks = [0, 1]  # третью заявку никто не умеет, в решатель она не идёт
    objective = build_objective_policy(instance, tasks, 1.0, order)
    lower_levels = len(tasks) * objective.regular_reward + objective.distance_weight

    assert objective.criteria == order
    assert objective.vehicle_cost > lower_levels
    # ярусы приоритетов остаются выше экономии бригад: авария бригаду оправдывает всегда
    assert objective.reward_for(RANK_EMERGENCY) > instance.n_engineers * objective.vehicle_cost


def test_dispatcher_can_prioritize_distance_over_engineer_count():
    instance = sample_instance()
    order = (
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
        ObjectiveCriterion.ENGINEERS_USED,
    )

    objective = build_objective_policy(instance, [0, 1], 1.0, order)

    assert objective.distance_weight > instance.n_engineers * objective.vehicle_cost


def test_distance_matrices_are_normalized_without_unreachable_sentinel():
    instance = sample_instance()
    instance.distance_km[CAR][0, 1] = 100_000.0
    instance.travel_min[CAR][0, 1] = 100_000

    inputs = build_solver_inputs(instance, [0, 1], distance_weight=1.0)

    assert inputs.objective.distance_scale < 100_000.0
    assert inputs.cost_matrices[CAR][0, 1] > 1.0  # остаётся непроходимо дорогим


def test_unsafe_float32_objective_is_rejected():
    request_count = 5_000
    fake_instance = SimpleNamespace(
        n_engineers=1,
        engineers=[SimpleNamespace(shift_start_min=0, shift_end_min=1_440)],
        # ярусы аварий и обычных заявок: на таком объёме Big-M выходит за float32
        requests=[
            SimpleNamespace(
                priority_level=EMERGENCY if index % 2 else REGULAR,
                objective_rank=RANK_EMERGENCY if index % 2 else RANK_NORMAL,
            )
            for index in range(request_count)
        ],
        distance_km={1: np.zeros((1, 1))},
        travel_min={1: np.zeros((1, 1))},
    )

    with pytest.raises(ValueError, match="float32"):
        build_objective_policy(fake_instance, list(range(request_count)), 1.0)


def test_route_table_becomes_ordered_visits():
    route_records = [
        # так выглядит get_route() у cuOpt 26.8
        {"truck_id": 1, "route": 0, "arrival_stamp": 540.0, "location": 1, "type": "Depot"},
        {"truck_id": 1, "route": 1, "arrival_stamp": 900.0, "location": 3, "type": "Delivery"},
        {"truck_id": 1, "route": 0, "arrival_stamp": 970.0, "location": 2, "type": "Delivery"},
    ]
    solution = parse_route_records(route_records, task_request_indices=[0, 1])

    assert list(solution.routes) == [1]
    visits = [(visit.request_index, visit.work_start_minute) for visit in solution.routes[1]]
    assert visits == [(1, 900.0), (0, 970.0)]


def test_three_priority_levels_are_strictly_ordered():
    """Авария важнее всех подключений дня, подключение — важнее всех обычных заявок."""
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),  # ремонт и дозаказ
            request(11, skill=1, window=("10:00", "12:00")),
            request(12, skill=1, window=("10:00", "12:00"), priority=CONNECTION),
            request(13, skill=1, window=("10:00", "12:00"), priority=CONNECTION),
            request(14, skill=1, window=("10:00", "12:00"), priority=CONNECTION),
            request(15, skill=1, window=("10:00", "12:00"), priority=EMERGENCY),
        ],
        skills={1: {1}},
    )

    objective = build_objective_policy(instance, list(range(6)), 1.0)
    emergency_bonus = objective.reward_for(RANK_EMERGENCY) - objective.regular_reward
    connection_bonus = objective.reward_for(RANK_HIGH) - objective.regular_reward

    assert emergency_bonus > connection_bonus > 0
    # одна авария перевешивает все три подключения, одно подключение — все обычные заявки
    assert emergency_bonus > 3 * connection_bonus
    assert connection_bonus > 6 * objective.regular_reward


def marked(request_id, *, priority=REGULAR, promised=False, moved=False):
    spec = request(request_id, skill=1, window=("10:00", "20:00"), priority=priority)
    return replace(spec, promised=promised, moved=moved)


def test_objective_ranks_follow_marks():
    """Ярусы A0-F0: авария, обещание, перенос, приоритет (docs/algoV2.md)."""
    assert marked(1, priority=EMERGENCY).objective_rank == RANK_EMERGENCY
    # авария остаётся аварией, даже если её обещали клиенту
    assert marked(2, priority=EMERGENCY, promised=True).objective_rank == RANK_EMERGENCY
    assert marked(3, promised=True).objective_rank == RANK_PROMISED
    assert marked(4, priority=CONNECTION, moved=True).objective_rank == RANK_MOVED_HIGH
    assert marked(5, moved=True).objective_rank == RANK_MOVED_NORMAL
    assert marked(6, priority=CONNECTION).objective_rank == RANK_HIGH
    assert marked(7).objective_rank == RANK_NORMAL


def test_promised_and_moved_requests_outrank_the_rest():
    """Обещанная сильнее всех нижних ярусов дня, перенесённая — всех неперенесённых."""
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            marked(10),
            marked(11),
            marked(12, priority=CONNECTION),
            marked(13, priority=CONNECTION),
            marked(14, priority=CONNECTION),
            marked(15, moved=True),
            marked(16, promised=True),
        ],
        skills={1: {1}},
    )

    objective = build_objective_policy(instance, list(range(7)), 1.0)

    def bonus(rank):
        return objective.reward_for(rank) - objective.regular_reward

    # в задаче: 1 обещанная, 1 перенесённая, 3 подключения, 2 обычные
    assert bonus(RANK_PROMISED) > bonus(RANK_MOVED_NORMAL) + 3 * bonus(RANK_HIGH)
    assert bonus(RANK_MOVED_NORMAL) > 3 * bonus(RANK_HIGH)
    assert bonus(RANK_HIGH) > 0
