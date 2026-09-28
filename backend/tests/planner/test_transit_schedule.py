"""План ОТ проверяется по реальному времени выезда, а не по утренней матрице."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest

from src.schemas.system import SolverParams
from src.services.planner import cuopt_solver, planner_loader, transit_schedule
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion
from src.services.planner.planner_problem import EngineerSpec, ProblemInstance, RequestSpec


def loaded_day():
    instance = ProblemInstance(
        engineers=[EngineerSpec(1, "Бригада", 4, 540, 700)],
        requests=[
            RequestSpec(10, 20, 550, 650, 1, None),
            RequestSpec(11, 20, 570, 590, 1, None),
        ],
        distance_km={4: np.zeros((3, 3))},
        travel_min={4: np.full((3, 3), 10, dtype=np.int32)},
    )
    instance.compatible[:] = True
    return planner_loader.LoadedDay(
        day=planner_loader.planning_day(date(2026, 9, 18)),
        office_id=1,
        instance=instance,
        engineers=[SimpleNamespace(start_latitude=55.7, start_longitude=37.6)],
        requests=[
            SimpleNamespace(latitude=55.71, longitude=37.61),
            SimpleNamespace(latitude=55.72, longitude=37.62),
        ],
        skill_names={},
        transport_names={},
    )


@pytest.mark.asyncio
async def test_retries_with_measured_travel_and_saves_actual_work_times():
    loaded = loaded_day()
    first = cuopt_solver.DaySolution(
        {0: [cuopt_solver.PlannedVisit(0, 550), cuopt_solver.PlannedVisit(1, 580)]}
    )
    second = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})

    async def route(points, transport, *, departure_time, allow_fallback):
        assert allow_fallback is False
        return SimpleNamespace(duration_min=30 if points[0].latitude == 55.71 else 10)

    with (
        patch.object(transit_schedule, "build_route", side_effect=route),
        patch.object(
            transit_schedule.cuopt_solver,
            "solve_day",
            AsyncMock(side_effect=[first, second]),
        ) as solve,
    ):
        result = await transit_schedule.solve_day(loaded, ())

    assert [visit.request_index for visit in result.routes[0]] == [1, 0]
    assert [visit.work_start_minute for visit in result.routes[0]] == [570, 600]
    assert solve.await_count == 2
    assert solve.await_args_list[1].args[0].travel_min[4][1, 2] == 30
    assert loaded.instance.travel_min[4][1, 2] == 10


@pytest.mark.asyncio
async def test_repair_respects_dispatcher_preference_for_fewer_brigades():
    loaded = loaded_day()
    loaded.instance.engineers.append(EngineerSpec(2, "Вторая", 4, 540, 700))
    loaded.engineers.append(SimpleNamespace(start_latitude=55.7, start_longitude=37.6))
    loaded.instance.travel_min[4] = np.full((4, 4), 10, dtype=np.int32)
    loaded.instance.distance_km[4] = np.ones((4, 4))
    loaded.instance.compatible = np.array([[True, False], [False, True]])
    original = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    prefer_fewer_brigades = (
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.ENGINEERS_USED,
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
    )

    with patch.object(
        transit_schedule, "build_route", AsyncMock(return_value=SimpleNamespace(duration_min=10))
    ):
        result = await transit_schedule.repair_unassigned(
            loaded, original, transit_schedule.node_points(loaded), {}, prefer_fewer_brigades, None
        )

    assert result is original


@pytest.mark.asyncio
async def test_missing_r5_route_during_insertion_keeps_verified_plan():
    loaded = loaded_day()
    original = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    request = httpx.Request("POST", "http://r5:8003/route")
    missing = httpx.HTTPStatusError(
        "Маршрут не найден", request=request, response=httpx.Response(404, request=request)
    )

    async def route(points, transport, *, departure_time, allow_fallback):
        if points[1].latitude == 55.72:
            raise missing
        return SimpleNamespace(duration_min=10)

    with patch.object(transit_schedule, "build_route", side_effect=route):
        result = await transit_schedule.repair_unassigned(
            loaded,
            original,
            transit_schedule.node_points(loaded),
            {},
            DEFAULT_OBJECTIVE_ORDER,
            None,
        )

    assert result is original


@pytest.mark.asyncio
async def test_unfixable_visit_is_left_unassigned():
    loaded = loaded_day()
    solution = cuopt_solver.DaySolution(
        {0: [cuopt_solver.PlannedVisit(0, 550), cuopt_solver.PlannedVisit(1, 580)]}
    )
    with (
        patch.object(
            transit_schedule,
            "build_route",
            AsyncMock(return_value=SimpleNamespace(duration_min=100)),
        ),
        patch.object(transit_schedule.cuopt_solver, "solve_day", AsyncMock(return_value=solution)),
    ):
        result = await transit_schedule.solve_day(loaded, ())

    assert [visit.request_index for visit in result.routes[0]] == [0]
    assert result.routes[0][0].work_start_minute == 640


@pytest.mark.asyncio
async def test_rechecks_next_leg_after_skipping_late_visit():
    loaded = loaded_day()
    loaded.instance.requests[0] = replace(loaded.instance.requests[0], window_end_min=560)
    loaded.instance.requests[1] = replace(loaded.instance.requests[1], window_end_min=690)
    solution = cuopt_solver.DaySolution(
        {0: [cuopt_solver.PlannedVisit(0, 550), cuopt_solver.PlannedVisit(1, 580)]}
    )

    async def route(points, transport, *, departure_time, allow_fallback):
        return SimpleNamespace(duration_min=30 if points[1].latitude == 55.71 else 10)

    with (
        patch.object(transit_schedule, "build_route", side_effect=route) as build,
        patch.object(transit_schedule.cuopt_solver, "solve_day", AsyncMock(return_value=solution)),
    ):
        # одна попытка: сразу снимаем визиты, к которым по расписанию не успеть
        result = await transit_schedule.solve_day(
            loaded, (), params=SolverParams(transit_attempts=1)
        )

    assert [visit.request_index for visit in result.routes[0]] == [1]
    assert result.routes[0][0].work_start_minute == 570
    # Проверили и вставку снятой заявки, но она всё равно не проходит своё окно.
    assert build.await_count == 3


@pytest.mark.asyncio
async def test_journal_explains_why_the_plan_goes_back_to_the_solver():
    """«Решили 66 из 66» ещё не значит «готово»: по журналу видно, что не сошлось и почему."""
    loaded = loaded_day()
    first = cuopt_solver.DaySolution(
        {0: [cuopt_solver.PlannedVisit(0, 550), cuopt_solver.PlannedVisit(1, 580)]}
    )
    second = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})

    async def route(points, transport, *, departure_time, allow_fallback):
        return SimpleNamespace(duration_min=30 if points[0].latitude == 55.71 else 10)

    with (
        patch.object(transit_schedule, "build_route", side_effect=route),
        patch.object(
            transit_schedule.cuopt_solver, "solve_day", AsyncMock(side_effect=[first, second])
        ),
        patch.object(transit_schedule.run_log, "note", AsyncMock()) as note,
    ):
        await transit_schedule.solve_day(loaded, ())

    written = [call.args[0] for call in note.await_args_list]
    # какой визит не сошёлся по фактическому расписанию
    assert any("№11" in line and "окно до" in line for line in written)
    # что изменилось в матрице и почему идём на новый круг
    assert any("Уточняю матрицу" in line for line in written)
    assert any("Решаю заново с уточнёнными временами" == line for line in written)
    assert any("Расписание сходится" in line for line in written)


@pytest.mark.asyncio
async def test_keeps_earlier_verified_plan_when_later_solver_drops_more_requests():
    loaded = loaded_day()
    loaded.instance.requests.append(RequestSpec(12, 20, 590, 590, 1, None))
    loaded.requests.append(SimpleNamespace(latitude=55.73, longitude=37.63))
    loaded.instance.travel_min[4] = np.full((4, 4), 5, dtype=np.int32)
    loaded.instance.distance_km[4] = np.ones((4, 4))
    loaded.instance.compatible = np.ones((3, 1), dtype=bool)
    first = cuopt_solver.DaySolution(
        {
            0: [
                cuopt_solver.PlannedVisit(0, 550),
                cuopt_solver.PlannedVisit(1, 580),
                cuopt_solver.PlannedVisit(2, 610),
            ]
        }
    )
    second = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})

    with (
        patch.object(
            transit_schedule,
            "build_route",
            AsyncMock(return_value=SimpleNamespace(duration_min=10)),
        ),
        patch.object(
            transit_schedule.cuopt_solver, "solve_day", AsyncMock(side_effect=[first, second])
        ),
        patch.object(transit_schedule.run_log, "note", AsyncMock()) as note,
    ):
        result = await transit_schedule.solve_day(loaded, DEFAULT_OBJECTIVE_ORDER)

    assert [visit.request_index for visit in result.routes[0]] == [0, 1]
    assert any("вариант попытки 1 лучше" in call.args[0] for call in note.await_args_list)


def test_checked_plan_comparison_respects_objective_order_and_override_ranks():
    loaded = loaded_day()
    instance = loaded.instance
    one = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    other = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(1, 580)]})
    # Во втором расчёте algoV2 ярусы могут быть переопределены извне.
    ranks = {0: 10, 1: 1}
    assert transit_schedule.checked_solution_score(
        instance, other, DEFAULT_OBJECTIVE_ORDER, ranks
    ) > (transit_schedule.checked_solution_score(instance, one, DEFAULT_OBJECTIVE_ORDER, ranks))


def test_checked_plan_comparison_respects_dispatcher_goal():
    loaded = loaded_day()
    instance = loaded.instance
    instance.engineers.append(EngineerSpec(2, "Вторая бригада", 4, 540, 700))
    instance.compatible = np.ones((2, 2), dtype=bool)
    instance.distance_km[4] = np.zeros((4, 4))
    spread = cuopt_solver.DaySolution(
        {
            0: [cuopt_solver.PlannedVisit(0, 550)],
            1: [cuopt_solver.PlannedVisit(1, 580)],
        }
    )
    compact = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    prefer_fewer_brigades = (
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.ENGINEERS_USED,
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
    )
    assert transit_schedule.checked_solution_score(
        instance, compact, prefer_fewer_brigades, None
    ) > transit_schedule.checked_solution_score(instance, spread, prefer_fewer_brigades, None)
