from datetime import date, datetime
from unittest.mock import patch

import pytest

from planner_test_helpers import engineer, make_instance, request
from src.core.errors import ExternalServiceError
from src.services.planner import cuopt_solver
from src.services.planner.cuopt_solver import DaySolution, PlannedVisit, validate_solution
from src.services.planner.planner_loader import planning_day


def instance():
    return make_instance(engineers=[engineer(1)],
                         requests=[request(10, skill=1, window=('10:00', '12:00'))],
                         skills={1: {1}})


def test_time_bounds_round_inwards():
    day = planning_day(date(2026, 8, 17))
    moment = datetime.fromisoformat('2026-08-17T10:00:30+03:00')
    assert day.to_minutes(moment, round_up=True) == 601
    assert day.to_minutes(moment) == 600
    assert day.to_minutes(datetime.fromisoformat('2026-08-16T23:59:30+03:00'), round_up=True) == 0


@pytest.mark.parametrize('visits', [
    [PlannedVisit(0, 100)],
    [PlannedVisit(0, float('nan'))],
    [PlannedVisit(0, 600), PlannedVisit(0, 700)],
    [PlannedVisit(99, 600)],
])
def test_rejects_invalid_solver_output(visits):
    with pytest.raises(ExternalServiceError):
        validate_solution(instance(), DaySolution(routes={0: visits}))


def test_accepts_valid_solver_output():
    validate_solution(instance(), DaySolution(routes={0: [PlannedVisit(0, 600)]}))


@pytest.mark.asyncio
async def test_runtime_failure_becomes_service_error():
    with patch.object(cuopt_solver, 'run_cuopt', side_effect=RuntimeError('CUDA unavailable')):
        with pytest.raises(ExternalServiceError, match='cuOpt'):
            await cuopt_solver.solve_day(instance())


def test_subminute_window_without_integer_start_is_not_sent():
    problem = instance()
    from dataclasses import replace
    problem.requests[0] = replace(problem.requests[0], window_start_min=601, window_end_min=600)
    assert cuopt_solver.schedulable_request_indices(problem) == []
