"""Память решений cuOpt: одинаковая задача — одинаковый ответ, без повторного поиска."""

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from planner_test_helpers import engineer, make_instance, request

from src.schemas.system import SolverParams
from src.services.planner import cuopt_solver, solver_memory


def instance():
    return make_instance(
        engineers=[engineer(1), engineer(2)],
        requests=[
            request(10, skill=1, window=("10:00", "12:00")),
            request(11, skill=1, window=("13:00", "15:00")),
        ],
        skills={1: {1}, 2: {1}},
    )


def inputs_of(problem, params=None):
    indices = cuopt_solver.schedulable_request_indices(problem)
    return cuopt_solver.build_solver_inputs(problem, indices, params=params or SolverParams())


def test_same_task_has_the_same_fingerprint():
    assert solver_memory.fingerprint(inputs_of(instance())) == solver_memory.fingerprint(
        inputs_of(instance())
    )


def test_any_change_gives_another_fingerprint():
    base = solver_memory.fingerprint(inputs_of(instance()))

    longer_travel = instance()
    longer_travel.travel_min[1] = longer_travel.travel_min[1].copy()
    longer_travel.travel_min[1][0, 2] += 1
    narrower = instance()
    from dataclasses import replace

    narrower.requests[1] = replace(narrower.requests[1], window_end_min=880)

    assert solver_memory.fingerprint(inputs_of(longer_travel)) != base
    assert solver_memory.fingerprint(inputs_of(narrower)) != base
    # другой лимит времени — диспетчер хочет искать иначе, ответ не берётся из памяти
    assert (
        solver_memory.fingerprint(inputs_of(instance(), SolverParams(time_limit_seconds=5))) != base
    )
    assert solver_memory.fingerprint(inputs_of(instance(), SolverParams(distance_weight=2))) != base


@pytest.mark.asyncio
async def test_remembered_task_is_not_solved_again():
    remembered = [
        {"truck_id": 0, "route": 0, "arrival_stamp": 600.0, "location": 2, "type": "Delivery"},
        {"truck_id": 1, "route": 1, "arrival_stamp": 780.0, "location": 3, "type": "Delivery"},
    ]
    with (
        patch.object(solver_memory, "recall", AsyncMock(return_value=remembered)),
        patch.object(solver_memory, "remember", AsyncMock()) as remember,
        patch.object(cuopt_solver, "run_cuopt") as run,
    ):
        solution = await cuopt_solver.solve_day(instance())

    run.assert_not_called()
    remember.assert_not_awaited()
    assert {
        index: [visit.request_index for visit in visits]
        for index, visits in solution.routes.items()
    } == {
        0: [0],
        1: [1],
    }


@pytest.mark.asyncio
async def test_new_task_is_solved_and_remembered():
    records = [
        {"truck_id": 0, "route": 0, "arrival_stamp": 600.0, "location": 2, "type": "Delivery"}
    ]
    with (
        patch.object(solver_memory, "recall", AsyncMock(return_value=None)),
        patch.object(solver_memory, "remember", AsyncMock()) as remember,
        patch.object(cuopt_solver, "run_cuopt", return_value=records) as run,
    ):
        await cuopt_solver.solve_day(instance())

    run.assert_called_once()
    assert remember.await_args.args[1] == records


def test_numpy_numbers_are_stored_exactly():
    record = {
        "truck_id": np.int32(1),
        "arrival_stamp": np.float64(601.123456789),
        "type": "Delivery",
    }

    plain = solver_memory._plain(record)

    assert plain == {"truck_id": 1, "arrival_stamp": 601.123456789, "type": "Delivery"}
    assert type(plain["truck_id"]) is int and type(plain["arrival_stamp"]) is float
