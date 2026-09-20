"""План ОТ проверяется по реальному времени выезда, а не по утренней матрице."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from src.core.errors import ExternalServiceError
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
async def test_rejects_unfixable_schedule():
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
        pytest.raises(ExternalServiceError, match="фактическому расписанию"),
    ):
        await transit_schedule.solve_day(loaded, ())
