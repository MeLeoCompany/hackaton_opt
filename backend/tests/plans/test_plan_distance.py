"""Общий пробег плана считается при построении и попадает в строку списка планов."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service
from src.services.planner.cuopt_solver import DaySolution, PlannedVisit


def loaded_day():
    engineers = [
        SimpleNamespace(start_latitude=55.70, start_longitude=37.60, transport_id=1),
        SimpleNamespace(start_latitude=55.80, start_longitude=37.70, transport_id=2),
    ]
    requests = [SimpleNamespace(latitude=55.71, longitude=37.61), SimpleNamespace(latitude=55.81, longitude=37.71)]
    return SimpleNamespace(engineers=engineers, requests=requests)


@pytest.mark.asyncio
async def test_distance_is_sum_of_engineer_routes():
    solution = DaySolution(routes={0: [PlannedVisit(0, 600)], 1: [PlannedVisit(1, 660)]})
    distances = iter([12.3456, 7.1])

    async def fake_route(points, transport):
        return SimpleNamespace(distance_km=next(distances))

    with patch.object(planning_service, 'build_route', side_effect=fake_route) as build_route:
        total = await planning_service.total_route_distance_km(loaded_day(), solution)

    assert total == 19.446
    assert build_route.await_count == 2


@pytest.mark.asyncio
async def test_engineer_without_visits_does_not_drive():
    with patch.object(planning_service, 'build_route', AsyncMock()) as build_route:
        total = await planning_service.total_route_distance_km(loaded_day(), DaySolution(routes={0: []}))

    assert total == 0
    build_route.assert_not_awaited()
