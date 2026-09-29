import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.schemas.travel import (
    Point,
    TransportKind,
    TravelLeg,
    TravelMatrix,
    TravelMode,
    TravelProvider,
)
from src.services.travel import travel_service

POINTS = [
    Point(latitude=55.78, longitude=37.68),
    Point(latitude=55.69, longitude=37.53),
]
DEPARTURE = datetime(2026, 9, 18, 9, tzinfo=UTC)


def surface_matrix() -> TravelMatrix:
    return TravelMatrix(
        transport=TransportKind.PUBLIC_TRANSPORT,
        provider=TravelProvider.VALHALLA,
        points=POINTS,
        distances_km=[[0, None], [16, 0]],
        durations_min=[[0, 60], [65, 0]],
    )


@pytest.mark.asyncio
async def test_public_transport_uses_r5_time_and_valhalla_distance():
    with (
        patch.object(
            travel_service.valhalla_provider,
            "build_matrix",
            AsyncMock(return_value=surface_matrix()),
        ),
        patch.object(
            travel_service.r5_provider,
            "build_duration_matrix",
            AsyncMock(return_value=[[0, 24], [None, 0]]),
        ) as r5_matrix,
        patch.object(travel_service, "_walking_matrix", AsyncMock(return_value=None)),
    ):
        result = await travel_service.build_matrix(
            POINTS,
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
            allow_fallback=False,
        )

    assert result.provider is TravelProvider.R5
    assert result.durations_min == [[0, 24], [None, 0]]
    assert result.distances_km[0][1] is not None
    assert result.distances_km[0][1] > 0
    assert result.distances_km[1][0] is None
    r5_matrix.assert_awaited_once_with(POINTS, DEPARTURE)


@pytest.mark.asyncio
async def test_public_transport_matrix_prefers_faster_direct_walk():
    walking = TravelMatrix(
        transport=TransportKind.PEDESTRIAN,
        provider=TravelProvider.VALHALLA,
        points=POINTS,
        distances_km=[[0, 1.2], [1.3, 0]],
        durations_min=[[0, 12], [13, 0]],
    )
    with (
        patch.object(
            travel_service.valhalla_provider,
            "build_matrix",
            AsyncMock(return_value=surface_matrix()),
        ),
        patch.object(
            travel_service.r5_provider,
            "build_duration_matrix",
            AsyncMock(return_value=[[0, 24], [None, 0]]),
        ),
        patch.object(travel_service, "_walking_matrix", AsyncMock(return_value=walking)),
    ):
        matrix = await travel_service.build_matrix(
            POINTS,
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
            allow_fallback=False,
        )

    assert matrix.durations_min == [[0, 12], [13, 0]]
    assert matrix.distances_km == [[0, 1.2], [1.3, 0]]


@pytest.mark.asyncio
async def test_public_transport_fallback_is_marked_explicitly():
    fallback = surface_matrix()
    with (
        patch.object(
            travel_service.valhalla_provider,
            "build_matrix",
            AsyncMock(return_value=surface_matrix()),
        ),
        patch.object(
            travel_service.r5_provider,
            "build_duration_matrix",
            AsyncMock(side_effect=httpx.ConnectError("R5 недоступен")),
        ),
        patch.object(travel_service, "_walking_matrix", AsyncMock(return_value=None)),
        patch.object(
            travel_service.transit_provider,
            "matrix_with_transit",
            return_value=fallback,
        ),
    ):
        result = await travel_service.build_matrix(
            POINTS,
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
        )

    assert result.provider is TravelProvider.TRANSIT_ESTIMATE


@pytest.mark.asyncio
async def test_public_transport_does_not_hide_r5_failure_in_strict_mode():
    with (
        patch.object(
            travel_service.valhalla_provider,
            "build_matrix",
            AsyncMock(return_value=surface_matrix()),
        ),
        patch.object(
            travel_service.r5_provider,
            "build_duration_matrix",
            AsyncMock(side_effect=httpx.ConnectError("R5 недоступен")),
        ),
        pytest.raises(httpx.ConnectError),
    ):
        await travel_service.build_matrix(
            POINTS,
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
            allow_fallback=False,
        )


@pytest.mark.asyncio
async def test_public_transport_route_uses_each_planned_departure():
    first_departure = DEPARTURE
    second_departure = datetime(2026, 9, 18, 11, tzinfo=UTC)
    result = travel_service.r5_provider.RouteResult(
        legs=[
            TravelLeg(
                distance_km=2,
                duration_min=12,
                mode=TravelMode.BUS,
                geometry="shape",
            )
        ],
        total_duration_min=15,
        walking_duration_min=1,
        waiting_duration_min=2,
        transit_duration_min=9,
        entry_exit_penalty_min=0,
        reliability_buffer_min=3,
        transfers=0,
    )
    points = [*POINTS, Point(latitude=55.75, longitude=37.61)]
    with patch.object(
        travel_service.r5_provider,
        "build_route",
        AsyncMock(side_effect=[result, result]),
    ) as r5_route:
        route = await travel_service.build_route(
            points,
            TransportKind.PUBLIC_TRANSPORT,
            leg_departure_times=[first_departure, second_departure],
            allow_fallback=False,
        )

    assert route.provider is TravelProvider.R5
    assert route.duration_min == 30
    assert route.distance_km == 4
    assert route.waiting_duration_min == 4
    assert route.geometry == ["shape", "shape"]
    assert [leg.visit_index for leg in route.legs] == [0, 1]
    calls = [call.args for call in r5_route.await_args_list]
    assert (points[0], points[1], first_departure) in calls
    assert (points[1], points[2], second_departure) in calls


@pytest.mark.asyncio
async def test_public_transport_route_preserves_leg_order_when_requests_finish_out_of_order():
    points = [*POINTS, Point(latitude=55.75, longitude=37.61)]

    def route_result(name: str, duration: float) -> travel_service.r5_provider.RouteResult:
        return travel_service.r5_provider.RouteResult(
            legs=[
                TravelLeg(
                    distance_km=1,
                    duration_min=duration,
                    mode=TravelMode.BUS,
                    geometry=name,
                )
            ],
            total_duration_min=duration,
            walking_duration_min=0,
            waiting_duration_min=0,
            transit_duration_min=duration,
            entry_exit_penalty_min=0,
            reliability_buffer_min=0,
            transfers=0,
        )

    async def cached_route(origin: Point, destination: Point, departure: datetime, build):
        del destination, departure, build
        if origin == points[0]:
            await asyncio.sleep(0.02)
            return route_result("first", 10)
        return route_result("second", 20)

    with patch.object(travel_service.travel_cache, "cached_route", side_effect=cached_route):
        route = await travel_service.build_route(
            points,
            TransportKind.PUBLIC_TRANSPORT,
            leg_departure_times=[DEPARTURE, DEPARTURE],
            allow_fallback=False,
        )

    assert route.geometry == ["first", "second"]
    assert [leg.visit_index for leg in route.legs] == [0, 1]
    assert route.duration_min == 30


@pytest.mark.asyncio
async def test_public_transport_zero_length_leg_has_no_wait_or_route_request():
    with patch.object(travel_service.r5_provider, "build_route", AsyncMock()) as r5_route:
        route = await travel_service.build_route(
            [POINTS[0], POINTS[0]],
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
            allow_fallback=False,
        )

    assert route.duration_min == 0
    assert route.distance_km == 0
    assert route.legs == []
    r5_route.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_transport_route_fallback_is_marked_explicitly():
    # Плечо длиной в 40 минут пешком: на коротких R5 не спрашивают вовсе
    # (r5_skip_when_walk_minutes), и подмены расписания оценкой не случилось бы
    estimated_leg = TravelLeg(distance_km=3, duration_min=40, geometry="shape")
    with (
        patch.object(
            travel_service.r5_provider,
            "build_route",
            AsyncMock(side_effect=httpx.ConnectError("R5 недоступен")),
        ),
        patch.object(
            travel_service.valhalla_provider,
            "route_legs",
            AsyncMock(return_value=[estimated_leg]),
        ),
        patch.object(travel_service, "_walking_legs", AsyncMock(return_value=None)),
        patch.object(
            travel_service.transit_provider,
            "legs_with_transit",
            return_value=[estimated_leg],
        ),
    ):
        route = await travel_service.build_route(
            POINTS,
            TransportKind.PUBLIC_TRANSPORT,
            departure_time=DEPARTURE,
        )

    assert route.provider is TravelProvider.TRANSIT_ESTIMATE
