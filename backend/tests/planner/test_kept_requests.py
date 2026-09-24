"""Ярус B нельзя выкинуть: проверка расписания выбирает вариант, где все его заявки на месте.

Решатель раскладывает день целиком, а проверка R5 снимает визит, который не успевает. Без
этого правила она могла снять заявку, уже стоявшую в плане, ради раскрытой — и после звонка
клиенту появлялась новая жертва (docs/algoV2.md, шаг 3).
"""

from types import SimpleNamespace

import numpy as np

from src.services.planner.cuopt_solver import DaySolution, PlannedVisit
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER
from src.services.planner.transit_schedule import checked_solution_score


def instance():
    """Два визита у одной бригады: №1 уже был в плане, №2 раскрытый."""
    requests = [
        SimpleNamespace(
            request_id=1, objective_rank=6, duration_min=30, window_start_min=0, window_end_min=900
        ),
        SimpleNamespace(
            request_id=2, objective_rank=6, duration_min=30, window_start_min=0, window_end_min=900
        ),
    ]
    engineers = [SimpleNamespace(transport_id=4)]
    return SimpleNamespace(
        requests=requests,
        engineers=engineers,
        n_requests=2,
        n_engineers=1,
        distance_km={4: np.zeros((3, 3))},
        compatible=np.ones((2, 1), dtype=bool),
        start_node=lambda index: 0,
        request_node=lambda index: index + 1,
    )


def score(solution, kept):
    return checked_solution_score(instance(), solution, DEFAULT_OBJECTIVE_ORDER, None, kept)


def test_variant_that_loses_a_kept_request_is_the_worst():
    with_kept = DaySolution({0: [PlannedVisit(0, 600)]})
    without_kept = DaySolution({0: [PlannedVisit(1, 600)]})

    assert score(with_kept, {1}) > score(without_kept, {1})


def test_more_requests_win_when_nobody_from_b_is_lost():
    both = DaySolution({0: [PlannedVisit(0, 600), PlannedVisit(1, 700)]})
    one = DaySolution({0: [PlannedVisit(0, 600)]})

    assert score(both, {1}) > score(one, {1})


def test_without_a_protected_tier_the_score_is_the_usual_one():
    one = DaySolution({0: [PlannedVisit(0, 600)]})
    other = DaySolution({0: [PlannedVisit(1, 600)]})

    assert score(one, set()) == score(other, set())
