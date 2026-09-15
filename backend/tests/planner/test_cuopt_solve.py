"""Настоящие расчёты cuOpt на маленьких задачах с заранее понятным ответом.

Нужна видеокарта NVIDIA и пакет cuopt; без него весь файл пропускается.
Каждый тест, кроме проверки конкретного ожидания, прогоняет решение через constraint_violations —
независимую проверку всех ограничений ТЗ. Для отладки удобно поставить брейкпоинт в
src/services/planner/cuopt_solver.py (build_solver_inputs, run_cuopt, parse_route_records).
"""

import pytest

pytest.importorskip("cuopt")

from planner_test_helpers import (  # noqa: E402
    BIKE,
    CAR,
    URGENT,
    WALK,
    assigned_request_ids,
    constraint_violations,
    engineer,
    hhmm,
    make_instance,
    request,
    route_request_ids,
    solve,
)

from src.core.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def short_time_limit(monkeypatch):
    # задачи крошечные — решателю хватает пары секунд, так тесты идут быстрее
    monkeypatch.setattr(settings, "cuopt_time_limit_seconds", 2.0)


def test_mixed_day_respects_all_constraints():
    skills = {1: {1, 2}, 2: {2}, 3: {2, 3}}
    instance = make_instance(
        engineers=[
            engineer(1, transport=CAR),
            engineer(2, transport=WALK, shift=("09:00", "18:00")),
            engineer(3, transport=BIKE, shift=("10:00", "20:00")),
        ],
        requests=[
            request(101, skill=1, window=("09:00", "11:00")),
            request(102, skill=2, window=("10:00", "12:00")),
            request(103, skill=2, window=("12:00", "14:00"), duration=45),
            request(104, skill=3, window=("14:00", "16:00"), duration=90),
            request(105, skill=2, window=("16:00", "18:00"), transport=CAR),
            request(106, skill=1, window=("13:00", "15:00"), priority=URGENT),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [101, 102, 103, 104, 105, 106]


def test_request_only_goes_to_engineer_with_skill():
    skills = {1: {1}, 2: {3}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[request(10, skill=3, window=("10:00", "12:00"))],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert route_request_ids(instance, solution, engineer_id=2) == [10]


def test_required_transport_goes_to_engineer_with_that_transport():
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1, transport=WALK), engineer(2, transport=CAR)],
        requests=[request(10, skill=1, window=("10:00", "12:00"), transport=CAR)],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert route_request_ids(instance, solution, engineer_id=2) == [10]


def test_request_nobody_is_qualified_for_stays_unassigned():
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=3, window=("10:00", "12:00")),  # аварийные — ни у кого нет
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10]


def test_impossible_request_is_dropped_and_the_rest_is_still_planned():
    # ночное окно раньше любой смены: выполнить нельзя, но из-за неё не должен падать весь план
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("02:00", "03:00")),
            request(12, skill=1, window=("14:00", "16:00")),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10, 12]


def test_work_must_finish_before_shift_end():
    # окно 17:30-18:00, работа час, смена до 18:00 — не успеть при любом раскладе
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1, shift=("08:00", "18:00"))],
        requests=[request(10, skill=1, window=("17:30", "18:00"), duration=60)],
        skills=skills,
    )

    solution = solve(instance)

    assert assigned_request_ids(instance, solution) == []


def test_first_visit_waits_for_drive_from_start():
    # смена с 09:00, до заявки 30 минут, окно открыто с 07:00 — начать можно не раньше 09:30
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1, shift=("09:00", "18:00"))],
        requests=[request(10, skill=1, window=("07:00", "12:00"))],
        skills=skills,
        travel_min=30,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    [visit] = solution.routes[0]
    assert visit.work_start_minute >= hhmm("09:30")


def test_next_visit_leaves_time_for_work_and_drive():
    # две заявки в одном окне у одного исполнителя: между началами — минимум час работы и 30 минут дороги
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "13:00")),
            request(11, skill=1, window=("10:00", "13:00")),
        ],
        skills=skills,
        travel_min=30,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    first_visit, second_visit = solution.routes[0]
    assert second_visit.work_start_minute - first_visit.work_start_minute >= 60 + 30


def test_urgent_request_wins_when_only_one_fits():
    # один исполнитель, обе заявки только в 10:00-10:40: вторая после первой уже не начнётся
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "10:40")),
            request(11, skill=1, window=("10:00", "10:40"), priority=URGENT),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [11]


def test_one_engineer_is_enough_when_he_can_do_everything():
    # за задействование каждого исполнителя платим — лишнего решатель брать не должен
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("14:00", "16:00")),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10, 11]
    assert len(solution.routes) == 1


def test_second_engineer_is_used_when_one_cannot_manage():
    # две заявки строго в одно и то же время — одному не разорваться
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "10:15")),
            request(11, skill=1, window=("10:00", "10:15")),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10, 11]
    assert len(solution.routes) == 2


def test_slow_transport_does_not_get_request_it_cannot_reach_in_time():
    # пешком до заявки 3 часа, на машине 20 минут; окно 09:00-09:30 при смене с 08:00
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1, transport=WALK), engineer(2, transport=CAR)],
        requests=[request(10, skill=1, window=("09:00", "09:30"))],
        skills=skills,
        travel_min_by_transport={WALK: 180, CAR: 20},
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert route_request_ids(instance, solution, engineer_id=2) == [10]
    assert route_request_ids(instance, solution, engineer_id=1) == []
