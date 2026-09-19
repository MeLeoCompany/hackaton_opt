from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.schemas.travel import Point, TransportKind, TravelMatrix, TravelProvider
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
