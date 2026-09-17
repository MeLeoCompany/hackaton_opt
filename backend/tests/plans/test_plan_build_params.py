"""Параметры расчёта: план строится тем решателем, который выбрал диспетчер."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.plans import SolverName
from src.services.planner import planning_service
from src.services.planner.cuopt_solver import DaySolution
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion


def patched_service(loaded, saved_plan):
    """Всё вокруг решателя подменено: проверяем только выбор решателя и что пишется в план."""
    return (
        patch.object(planning_service, "load_planning_day", AsyncMock(return_value=loaded)),
        patch.object(planning_service, "save_solution", AsyncMock(return_value=saved_plan)),
        patch.object(
            planning_service,
            "total_route_distance",
            AsyncMock(return_value=planning_service.PlanDistance(12.0, "valhalla")),
        ),
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=["сводка"])),
    )


@pytest.mark.asyncio
async def test_cuopt_is_used_by_default():
    loaded = SimpleNamespace(instance="задача дня")
    plan = SimpleNamespace(total_distance_km=None, distance_provider=None)
    session = SimpleNamespace(commit=AsyncMock())
    load, save, distance, summarize = patched_service(loaded, plan)

    with (
        load,
        save as save_solution,
        distance,
        summarize,
        patch.object(
            planning_service.cuopt_solver, "solve_day", AsyncMock(return_value=DaySolution())
        ) as cuopt,
        patch.object(planning_service.baseline_solver, "solve_day") as baseline,
    ):
        await planning_service.build_plan_for_day(session, "2026-08-17")

    cuopt.assert_awaited_once_with("задача дня", objective_order=DEFAULT_OBJECTIVE_ORDER)
    baseline.assert_not_called()
    assert save_solution.await_args.kwargs["solver"] == "cuopt"
    assert save_solution.await_args.kwargs["solve_duration_ms"] >= 0
    assert save_solution.await_args.kwargs["objective_order"] == DEFAULT_OBJECTIVE_ORDER


@pytest.mark.asyncio
async def test_baseline_is_used_when_chosen():
    loaded = SimpleNamespace(instance="задача дня")
    plan = SimpleNamespace(total_distance_km=None, distance_provider=None)
    session = SimpleNamespace(commit=AsyncMock())
    load, save, distance, summarize = patched_service(loaded, plan)

    with (
        load,
        save as save_solution,
        distance,
        summarize,
        patch.object(planning_service.cuopt_solver, "solve_day", AsyncMock()) as cuopt,
        patch.object(
            planning_service.baseline_solver, "solve_day", return_value=DaySolution()
        ) as baseline,
    ):
        await planning_service.build_plan_for_day(session, "2026-08-17", SolverName.BASELINE)

    baseline.assert_called_once_with("задача дня")
    cuopt.assert_not_awaited()
    assert save_solution.await_args.kwargs["solver"] == "baseline"
    assert save_solution.await_args.kwargs["run_type"].value == "baseline"
    assert save_solution.await_args.kwargs["objective_order"] is None


@pytest.mark.asyncio
async def test_custom_objective_order_is_forwarded_and_saved():
    loaded = SimpleNamespace(instance="задача дня")
    plan = SimpleNamespace(total_distance_km=None, distance_provider=None)
    session = SimpleNamespace(commit=AsyncMock())
    load, save, distance, summarize = patched_service(loaded, plan)
    order = [
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
        ObjectiveCriterion.ENGINEERS_USED,
    ]

    with (
        load,
        save as save_solution,
        distance,
        summarize,
        patch.object(
            planning_service.cuopt_solver,
            "solve_day",
            AsyncMock(return_value=DaySolution()),
        ) as cuopt,
    ):
        await planning_service.build_plan_for_day(session, "2026-08-17", SolverName.CUOPT, order)

    expected = tuple(order)
    cuopt.assert_awaited_once_with("задача дня", objective_order=expected)
    assert save_solution.await_args.kwargs["objective_order"] == expected


@pytest.mark.asyncio
async def test_single_plan_without_pair():
    """Пары планов расчёт больше не создаёт: сравнить можно любые два готовых плана."""
    loaded = SimpleNamespace(instance="задача дня")
    plan = SimpleNamespace(total_distance_km=None, distance_provider=None)
    session = SimpleNamespace(commit=AsyncMock())
    load, save, distance, summarize = patched_service(loaded, plan)

    with (
        load,
        save as save_solution,
        distance,
        summarize,
        patch.object(
            planning_service.cuopt_solver, "solve_day", AsyncMock(return_value=DaySolution())
        ),
    ):
        await planning_service.build_plan_for_day(session, "2026-08-17")

    assert save_solution.await_count == 1
    assert "comparison_id" not in save_solution.await_args.kwargs
