"""Настоящие расчёты OR-Tools на маленьких задачах с заранее понятным ответом.

Постановка та же, что у cuOpt, поэтому и ожидания те же: ограничения ТЗ соблюдаются, аварийная
заявка важнее обычных, лишнюю бригаду ради обычной заявки не выводим. Видеокарта не нужна —
OR-Tools считает на процессоре. Каждый тест, кроме своего ожидания, прогоняет решение через
constraint_violations: независимую проверку всех ограничений.
"""

import asyncio

from planner_test_helpers import (
    CAR,
    URGENT,
    WALK,
    assigned_request_ids,
    constraint_violations,
    engineer,
    make_instance,
    request,
    route_request_ids,
)

from src.schemas.system import SolverParams
from src.services.planner import ortools_solver
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion

# задачи крошечные: секунды поиска хватает с запасом
PARAMS = SolverParams(time_limit_seconds=1.0)


def solve(instance, objective_order=DEFAULT_OBJECTIVE_ORDER):
    return asyncio.run(
        ortools_solver.solve_day(instance, objective_order=objective_order, params=PARAMS)
    )


def test_mixed_day_respects_all_constraints():
    skills = {1: {1, 2}, 2: {2}}
    instance = make_instance(
        engineers=[engineer(1, transport=CAR), engineer(2, transport=WALK)],
        requests=[
            request(101, skill=1, window=("09:00", "11:00")),
            request(102, skill=2, window=("10:00", "12:00")),
            request(103, skill=2, window=("12:00", "14:00"), duration=45),
            request(104, skill=1, window=("13:00", "15:00"), priority=URGENT),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [101, 102, 103, 104]


def test_request_only_goes_to_engineer_with_skill():
    skills = {1: {1}, 2: {3}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[request(10, skill=3, window=("10:00", "12:00"))],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert route_request_ids(instance, solution, 2) == [10]


def test_required_transport_goes_to_engineer_with_that_transport():
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1, transport=WALK), engineer(2, transport=CAR)],
        requests=[request(10, skill=1, window=("10:00", "12:00"), transport=CAR)],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert route_request_ids(instance, solution, 2) == [10]


def test_request_nobody_is_qualified_for_stays_unassigned():
    """Невыполнимая заявка не срывает расчёт: остальное всё равно раскладывается."""
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=3, window=("10:00", "12:00")),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10]


def test_work_must_finish_before_shift_end():
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1, shift=("09:00", "11:00"))],
        requests=[request(10, skill=1, window=("10:30", "12:00"), duration=60)],
        skills=skills,
    )

    solution = solve(instance)

    assert assigned_request_ids(instance, solution) == []


def test_urgent_request_wins_when_only_one_fits():
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


def test_one_urgent_request_wins_over_two_regular_requests():
    """Иерархия ТЗ: авария важнее общего количества обычных заявок."""
    skills = {1: {1}}
    instance = make_instance(
        engineers=[engineer(1, shift=("10:00", "11:30"))],
        requests=[
            request(10, skill=1, window=("10:00", "11:00"), duration=30),
            request(11, skill=1, window=("10:00", "11:00"), duration=30),
            request(12, skill=1, window=("10:00", "11:00"), duration=90, priority=URGENT),
        ],
        skills=skills,
        travel_min=0,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [12]


def test_crews_first_keeps_one_brigade_instead_of_taking_both_requests():
    """«Меньше бригад» сразу после приоритетов: вторую бригаду ради обычной заявки не выводим."""
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "11:00"), duration=60),
            request(11, skill=1, window=("10:00", "11:00"), duration=60),
        ],
        skills=skills,
    )

    solution = solve(
        instance,
        (
            ObjectiveCriterion.URGENT_REQUESTS,
            ObjectiveCriterion.ENGINEERS_USED,
            ObjectiveCriterion.ASSIGNED_REQUESTS,
            ObjectiveCriterion.TRAVEL_DISTANCE,
        ),
    )

    assert constraint_violations(instance, skills, solution) == []
    assert len(solution.routes) == 1


def test_second_engineer_is_used_when_one_cannot_manage():
    skills = {1: {1}, 2: {1}}
    instance = make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "11:00"), duration=60),
            request(11, skill=1, window=("10:00", "11:00"), duration=60),
        ],
        skills=skills,
    )

    solution = solve(instance)

    assert constraint_violations(instance, skills, solution) == []
    assert assigned_request_ids(instance, solution) == [10, 11]
    assert len(solution.routes) == 2
