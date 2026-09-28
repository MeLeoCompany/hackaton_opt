"""Ярусы круга: второй и третий расчёты считают по одной шкале (docs/algoV2.md, шаги 3 и 5).

A — аварии, B — кто влез в первый расчёт, C — раскрытые (те, по кому звонили). Внутри
ярусов обычный порядок: обещание, перенос, приоритет.
"""

from types import SimpleNamespace

from src.services.planner.planner_problem import (
    RANK_EMERGENCY,
    RANK_NORMAL,
    RANK_PROMISED,
    WIDENED_RANK_SHIFT,
    round_ranks,
)


def request(request_id, *, level=3, promised=False):
    rank = RANK_EMERGENCY if level == 1 else RANK_PROMISED if promised else RANK_NORMAL
    return SimpleNamespace(request_id=request_id, priority_level=level, objective_rank=rank)


def test_placed_requests_stand_above_the_widened_ones():
    """B выше C: раскрытая заявка не вправе выкинуть ту, что уже влезла."""
    requests = [request(1), request(2)]

    ranks = round_ranks(requests, kept_request_ids={1})

    assert ranks[0] == RANK_NORMAL
    assert ranks[1] == RANK_NORMAL + WIDENED_RANK_SHIFT
    assert ranks[0] < ranks[1]  # меньше номер — важнее ярус


def test_emergency_is_on_top_wherever_it_came_from():
    """A1: авария вправе подвинуть обычную заявку, даже если сама не влезла."""
    requests = [request(1), request(2, level=1)]

    ranks = round_ranks(requests, kept_request_ids={1})

    assert ranks[1] == RANK_EMERGENCY
    assert ranks[1] < ranks[0]


def test_promised_goes_first_among_the_widened():
    """Внутри C порядок обычный: согласованная выше просто раскрытой."""
    requests = [request(1), request(2, promised=True), request(3)]

    ranks = round_ranks(requests, kept_request_ids={1})

    assert ranks[1] == RANK_PROMISED + WIDENED_RANK_SHIFT
    assert ranks[1] < ranks[2]
    assert ranks[0] < ranks[1]  # но всё равно ниже тех, кто уже в плане
