"""Маршруты плана строятся один раз и лежат в кеше: открытие плана не ходит в маршрутизатор."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.travel import TransportKind, TravelProvider, TravelRoute
from src.services.planner import planning_service

DAY = datetime(2026, 9, 18, tzinfo=UTC)
CAR = TransportKind.CAR.value
TRANSIT = TransportKind.PUBLIC_TRANSPORT.value


def engineer(engineer_id=1, transport=CAR):
    return SimpleNamespace(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        start_latitude=55.70,
        start_longitude=37.60,
        transport_id=transport,
        shift_start=DAY + timedelta(hours=9),
        shift_end=DAY + timedelta(hours=18),
    )


def visit(crew, order, request_id, start_hour, duration=45):
    return SimpleNamespace(
        engineer=crew,
        engineer_id=crew.id,
        visit_order=order,
        planned_arrival_time=DAY + timedelta(hours=start_hour),
        request_id=request_id,
        request=SimpleNamespace(
            id=request_id,
            latitude=55.71 + order / 100,
            longitude=37.61,
            duration_minutes=duration,
        ),
    )


def travel(distance=3.0, provider=TravelProvider.VALHALLA):
    return TravelRoute(
        transport=TransportKind.CAR,
        provider=provider,
        distance_km=distance,
        duration_min=12,
        geometry=["abc"],
    )


async def build(assignments, cached=None, **kwargs):
    """Строит маршруты плана: маршрутизатор, кеш и сборка визитов подменены."""
    plan = SimpleNamespace(id=22, input_snapshot=None)
    saved = []

    async def remember(session, plan_id, engineer_id, fingerprint, route):
        saved.append((engineer_id, fingerprint, route))

    with (
        patch.object(
            planning_service.plans_repository,
            "list_cached_routes",
            AsyncMock(return_value=cached or {}),
        ),
        patch.object(planning_service.plans_repository, "save_cached_route", side_effect=remember),
        patch.object(planning_service, "route_visits", return_value=[]),
        patch.object(planning_service, "candidate_engineers_by_request", return_value={}),
        patch.object(planning_service, "build_route", **kwargs) as build_route,
    ):
        routes, built = await planning_service.plan_routes(object(), plan, assignments)
    return routes, built, saved, build_route


@pytest.mark.asyncio
async def test_route_is_built_once_and_cached():
    crew = engineer()
    assignments = [visit(crew, 1, 10, 10), visit(crew, 2, 11, 12)]

    routes, built, saved, build_route = await build(assignments, return_value=travel(12.3456))

    assert built is True
    assert build_route.await_count == 1
    assert [engineer_id for engineer_id, _, _ in saved] == [1]
    assert routes[0].distance_km == 12.3456


@pytest.mark.asyncio
async def test_cached_route_is_taken_without_the_router():
    """Открытие плана: маршрут уже построен при расчёте — маршрутизатор не нужен."""
    crew = engineer()
    assignments = [visit(crew, 1, 10, 10)]
    _, _, saved, _ = await build(assignments, return_value=travel(7.1))
    _, fingerprint, route = saved[0]
    cached = {1: SimpleNamespace(fingerprint=fingerprint, travel=route)}

    routes, built, again, build_route = await build(assignments, cached, return_value=travel(99))

    assert built is False
    build_route.assert_not_awaited()
    assert again == []
    assert routes[0].distance_km == 7.1


@pytest.mark.asyncio
async def test_route_is_rebuilt_when_its_points_changed():
    crew = engineer()
    stale = {1: SimpleNamespace(fingerprint="другой маршрут", travel=travel(1).model_dump())}

    routes, built, _, build_route = await build(
        [visit(crew, 1, 10, 10)], stale, return_value=travel(4.2)
    )

    assert built is True
    assert build_route.await_count == 1
    assert routes[0].distance_km == 4.2


def test_plan_distance_is_sum_of_routes_and_keeps_fallback_visible():
    routes = [
        SimpleNamespace(distance_km=12.3456, provider="valhalla"),
        SimpleNamespace(distance_km=7.1, provider="haversine"),
    ]

    total = planning_service.routes_distance(routes)

    assert total.distance_km == 19.446
    assert total.provider == "mixed"
    assert planning_service.routes_distance([]).provider is None


def test_public_transport_departs_when_previous_work_is_done():
    crew = engineer(transport=TRANSIT)
    ordered = [visit(crew, 1, 10, 10, duration=45), visit(crew, 2, 11, 12)]

    _, transport, departures = planning_service.route_request(ordered)

    assert transport is TransportKind.PUBLIC_TRANSPORT
    assert departures == [crew.shift_start, DAY + timedelta(hours=10, minutes=45)]


def test_roads_and_timetable_together_are_not_an_estimate():
    """Автомобиль по Valhalla и ОТ по R5 — оба настоящий расчёт, а не «приближённо»."""
    routes = [
        SimpleNamespace(distance_km=5.0, provider="valhalla"),
        SimpleNamespace(distance_km=7.8, provider="r5"),
    ]

    assert planning_service.routes_distance(routes).provider == "routed"
    assert planning_service.routes_distance(routes[1:]).provider == "r5"
