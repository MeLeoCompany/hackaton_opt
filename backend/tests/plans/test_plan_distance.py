"""Общий пробег плана считается при построении и попадает в строку списка планов."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.travel import TravelProvider
from src.services.planner import planning_service
from src.services.planner.cuopt_solver import DaySolution, PlannedVisit


def loaded_day():
    engineers = [
        SimpleNamespace(start_latitude=55.70, start_longitude=37.60, transport_id=1),
        SimpleNamespace(start_latitude=55.80, start_longitude=37.70, transport_id=2),
    ]
    requests = [
        SimpleNamespace(latitude=55.71, longitude=37.61),
        SimpleNamespace(latitude=55.81, longitude=37.71),
    ]
    return SimpleNamespace(engineers=engineers, requests=requests)


@pytest.mark.asyncio
async def test_distance_is_sum_of_engineer_routes():
    solution = DaySolution(routes={0: [PlannedVisit(0, 600)], 1: [PlannedVisit(1, 660)]})
    distances = iter([12.3456, 7.1])

    async def fake_route(points, transport):
        return SimpleNamespace(distance_km=next(distances), provider=TravelProvider.VALHALLA)

    with patch.object(planning_service, "build_route", side_effect=fake_route) as build_route:
        total = await planning_service.total_route_distance(loaded_day(), solution)

    assert total.distance_km == 19.446
    assert total.provider == "valhalla"
    assert build_route.await_count == 2


@pytest.mark.asyncio
async def test_engineer_without_visits_does_not_drive():
    with patch.object(planning_service, "build_route", AsyncMock()) as build_route:
        total = await planning_service.total_route_distance(
            loaded_day(), DaySolution(routes={0: []})
        )

    assert total.distance_km == 0
    assert total.provider is None
    build_route.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_provider_is_preserved_for_plan_summary():
    solution = DaySolution(routes={0: [PlannedVisit(0, 600)], 1: [PlannedVisit(1, 660)]})
    providers = iter([TravelProvider.VALHALLA, TravelProvider.HAVERSINE])

    async def fake_route(points, transport):
        return SimpleNamespace(distance_km=1.0, provider=next(providers))

    with patch.object(planning_service, "build_route", side_effect=fake_route):
        total = await planning_service.total_route_distance(loaded_day(), solution)

    assert total.distance_km == 2.0
    assert total.provider == "mixed"


@pytest.mark.asyncio
async def test_public_transport_route_uses_service_completion_as_next_departure():
    day_start = datetime(2026, 9, 18, tzinfo=UTC)
    shift_start = day_start + timedelta(hours=9)
    loaded = SimpleNamespace(
        engineers=[
            SimpleNamespace(
                start_latitude=55.7,
                start_longitude=37.6,
                transport_id=4,
                shift_start=shift_start,
            )
        ],
        requests=[
            SimpleNamespace(latitude=55.71, longitude=37.61, duration_minutes=45),
            SimpleNamespace(latitude=55.72, longitude=37.62, duration_minutes=30),
        ],
        day=SimpleNamespace(from_minutes=lambda minutes: day_start + timedelta(minutes=minutes)),
    )
    solution = DaySolution(routes={0: [PlannedVisit(0, 600), PlannedVisit(1, 720)]})
    travel = SimpleNamespace(distance_km=3, provider=TravelProvider.R5)

    with patch.object(
        planning_service, "build_route", AsyncMock(return_value=travel)
    ) as build_route:
        await planning_service.total_route_distance(loaded, solution)

    assert build_route.await_args.kwargs["leg_departure_times"] == [
        shift_start,
        day_start + timedelta(minutes=645),
    ]
