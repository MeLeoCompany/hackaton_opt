"""План ОТ проверяется по реальному времени выезда, а не по утренней матрице."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from src.services.planner import cuopt_solver, planner_loader, transit_schedule
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

    assert result.routes[0][0].work_start_minute == 550
    assert solve.await_count == 2
    assert solve.await_args_list[1].args[0].travel_min[4][1, 2] == 30
    assert loaded.instance.travel_min[4][1, 2] == 10


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
        patch.object(transit_schedule.settings, "transit_plan_max_attempts", 1),
    ):
        result = await transit_schedule.solve_day(loaded, ())

    assert [visit.request_index for visit in result.routes[0]] == [1]
    assert result.routes[0][0].work_start_minute == 570
    assert build.await_count == 2


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
