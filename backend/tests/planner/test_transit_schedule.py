"""План ОТ проверяется по реальному времени выезда, а не по утренней матрице."""

import asyncio
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
async def test_independent_team_routes_are_checked_concurrently():
    loaded = loaded_day()
    loaded.instance.engineers.append(EngineerSpec(2, "Вторая", 4, 540, 700))
    loaded.engineers.append(SimpleNamespace(start_latitude=55.7, start_longitude=37.6))
    loaded.instance.travel_min[4] = np.full((4, 4), 10, dtype=np.int32)
    loaded.instance.distance_km[4] = np.ones((4, 4))
    loaded.instance.compatible = np.ones((2, 2), dtype=bool)
    solution = cuopt_solver.DaySolution(
        {
            0: [cuopt_solver.PlannedVisit(0, 550)],
            1: [cuopt_solver.PlannedVisit(1, 570)],
        }
    )
    active = 0
    maximum_active = 0

    async def route(*args, **kwargs):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(duration_min=10)

    with (
        patch.object(transit_schedule, "build_route", side_effect=route),
        patch.object(transit_schedule.run_log, "note", AsyncMock()) as note,
    ):
        checked, _ = await transit_schedule.check_schedule(
            loaded,
            solution,
            transit_schedule.node_points(loaded),
            transit_schedule.LegDurationCache(),
        )

    assert checked == solution
    assert maximum_active == 2
    progress = [
        call.args[0]
        for call in note.await_args_list
        if call.args[0].startswith("R5: маршрут ")
    ]
    assert sorted(line.split(" — ")[0] for line in progress) == [
        "R5: маршрут 1 из 2",
        "R5: маршрут 2 из 2",
    ]


@pytest.mark.asyncio
async def test_identical_concurrent_legs_share_one_r5_request():
    loaded = loaded_day()
    points = transit_schedule.node_points(loaded)
    cache = transit_schedule.LegDurationCache()
    release = asyncio.Event()

    async def route(*args, **kwargs):
        await release.wait()
        return SimpleNamespace(duration_min=10)

    with patch.object(transit_schedule, "build_route", side_effect=route) as build:
        first = asyncio.create_task(
            transit_schedule.leg_duration(loaded, points, cache, 0, 0, 1, 540)
        )
        second = asyncio.create_task(
            transit_schedule.leg_duration(loaded, points, cache, 0, 0, 1, 540)
        )
        await asyncio.sleep(0)
        release.set()
        assert await asyncio.gather(first, second) == [10, 10]

    build.assert_awaited_once()


@pytest.mark.asyncio
async def test_insertion_candidates_are_checked_concurrently_in_stable_order():
    loaded = loaded_day()
    loaded.instance.engineers.append(EngineerSpec(2, "Вторая", 4, 540, 700))
    loaded.engineers.append(SimpleNamespace(start_latitude=55.7, start_longitude=37.6))
    loaded.instance.travel_min[4] = np.full((4, 4), 10, dtype=np.int32)
    loaded.instance.distance_km[4] = np.ones((4, 4))
    loaded.instance.compatible = np.ones((2, 2), dtype=bool)
    original = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    active = 0
    maximum_active = 0

    async def insert(loaded, solution, points, cache, engineer_index, position, request_index):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        # Обратный порядок завершения не должен менять выбор при равной оценке.
        await asyncio.sleep(0.02 if engineer_index == 0 else 0.01)
        active -= 1
        return [
            *solution.routes.get(engineer_index, []),
            cuopt_solver.PlannedVisit(request_index, 580),
        ]

    with patch.object(transit_schedule, "inserted_route", side_effect=insert):
        result = await transit_schedule.repair_unassigned(
            loaded,
            original,
            transit_schedule.node_points(loaded),
            transit_schedule.LegDurationCache(),
            DEFAULT_OBJECTIVE_ORDER,
            None,
        )

    assert maximum_active > 1
    assert [visit.request_index for visit in result.routes[0]] == [0, 1]
    assert 1 not in result.routes


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
            loaded,
            original,
            transit_schedule.node_points(loaded),
            transit_schedule.LegDurationCache(),
            prefer_fewer_brigades,
            None,
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
            transit_schedule.LegDurationCache(),
            DEFAULT_OBJECTIVE_ORDER,
            None,
        )

    assert result is original


@pytest.mark.asyncio
async def test_insertion_does_not_reuse_consumed_equipment():
    loaded = loaded_day()
    loaded.instance.engineers[0] = replace(loaded.instance.engineers[0], equipment_capacity={7: 1})
    loaded.instance.requests[0] = replace(loaded.instance.requests[0], equipment_demand={7: 1})
    loaded.instance.requests[1] = replace(loaded.instance.requests[1], equipment_demand={7: 1})
    solution = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})

    with patch.object(transit_schedule, "build_route", AsyncMock()) as build:
        route = await transit_schedule.inserted_route(
            loaded,
            solution,
            transit_schedule.node_points(loaded),
            transit_schedule.LegDurationCache(),
            engineer_index=0,
            position=1,
            request_index=1,
        )

    assert route is None
    build.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_fallback_wins_when_new_solution_loses_kept_request():
    """Раскрытое окно не должно вытеснять заявку из уже проверенного плана."""
    loaded = loaded_day()
    candidate = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(1, 570)]})
    fallback = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})

    with patch.object(
        transit_schedule,
        "repair_unassigned",
        AsyncMock(side_effect=[candidate, fallback]),
    ):
        result = await transit_schedule.finish_solution(
            loaded,
            candidate,
            transit_schedule.node_points(loaded),
            transit_schedule.LegDurationCache(),
            DEFAULT_OBJECTIVE_ORDER,
            None,
            {10},
            fallback,
        )

    assert result is fallback


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


@pytest.mark.asyncio
async def test_unchanged_matrix_keeps_protected_requests_during_repair():
    """На раннем выходе из итераций доразмещение не должно забывать ярус B."""
    loaded = loaded_day()
    solution = cuopt_solver.DaySolution({0: [cuopt_solver.PlannedVisit(0, 550)]})
    kept = {10}

    with (
        patch.object(transit_schedule, "counted_check", AsyncMock(return_value=(None, {}))),
        patch.object(
            transit_schedule,
            "check_schedule",
            AsyncMock(return_value=(solution, {})),
        ),
        patch.object(
            transit_schedule,
            "repair_unassigned",
            AsyncMock(return_value=solution),
        ) as repair,
    ):
        result = await transit_schedule.solve_day(
            loaded,
            DEFAULT_OBJECTIVE_ORDER,
            solve=AsyncMock(return_value=solution),
            kept_request_ids=kept,
        )

    assert result is solution
    assert repair.await_args.args[-1] == kept


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
