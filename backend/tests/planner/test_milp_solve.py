"""Задача целиком: собрать, решить HiGHS, проверить план."""

from milp_test_helpers import URGENT, engineer, hhmm, make_instance, read_plan, request, solve

from src.services.planner import build_milp


def plan_for(instance):
    problem = build_milp(instance)
    values = solve(problem)
    return read_plan(problem, instance, values)


def test_basic_plan(basic_instance):
    routes, unassigned = plan_for(basic_instance)

    assert unassigned == []
    assert routes == {
        1: [(hhmm("10:00"), 10), (hhmm("15:00"), 11)],
        2: [(hhmm("10:00"), 12)],
    }


def test_next_visit_waits_for_work_and_travel():
    # обе заявки в одном окне: вторая начнётся не раньше 10:00 + 60 работы + 10 дороги
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("10:00", "12:00")),
        ],
        skills={1: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == []
    (first, _), (second, _) = routes[1]
    assert second - first >= 60 + 10


def test_second_visit_does_not_fit_after_drive_from_start():
    # Смена с 10:00, до первой заявки 10 минут дороги -> начать её можно только в 10:10.
    # Вторая тогда не раньше 10:10 + 60 + 10 = 11:20, а её окно закрывается в 11:10.
    #
    # Переезд 10 -> 11 при этом НЕ отсечён: отсечение смотрит на начало окна (10:00 + 70 = 11:10),
    # и дорогу со старта не учитывает. Значит отказ даёт именно временное ограничение.
    instance = make_instance(
        engineers=[engineer(1, shift=("10:00", "18:00"))],
        requests=[
            request(10, skill=1, window=("10:00", "11:00")),
            request(11, skill=1, window=("10:00", "11:10")),
        ],
        skills={1: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert len(unassigned) == 1
    assert len(routes[1]) == 1


def test_request_without_qualified_engineer_is_unassigned():
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=3, window=("10:00", "12:00")),  # аварийные — ни у кого нет
        ],
        skills={1: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == [11]
    assert [request_id for _, request_id in routes[1]] == [10]


def test_required_transport_is_respected():
    instance = make_instance(
        engineers=[engineer(1, transport=2), engineer(2, transport=1)],
        requests=[request(10, skill=1, window=("10:00", "12:00"), transport=1)],
        skills={1: {1}, 2: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == []
    assert list(routes) == [2]  # только у инженера 2 есть автомобиль


def test_work_must_end_before_shift_end():
    instance = make_instance(
        engineers=[engineer(1, shift=("08:00", "18:00"))],
        requests=[request(10, skill=1, window=("17:30", "18:00"), duration=60)],
        skills={1: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == [10]
    assert routes == {}


def test_urgent_request_wins_conflict():
    # окно 10:00-10:40: успеть обе нельзя (60 работы + 10 дороги > 40)
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "10:40")),
            request(11, skill=1, window=("10:00", "10:40"), priority=URGENT),
        ],
        skills={1: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == [10]
    assert [request_id for _, request_id in routes[1]] == [11]


def test_uses_fewer_engineers_when_possible():
    # один инженер успевает обе заявки — второго задействовать незачем
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("14:00", "16:00")),
        ],
        skills={1: {1}, 2: {1}},
    )
    routes, unassigned = plan_for(instance)

    assert unassigned == []
    assert len(routes) == 1
