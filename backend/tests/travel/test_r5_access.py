from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.schemas.travel import Point, TravelLeg, TravelMode
from src.services.travel import r5_access, r5_provider

ORIGIN = Point(latitude=55.7, longitude=37.5)
DESTINATION = Point(latitude=55.8, longitude=37.6)
DEPARTURE = datetime(2026, 9, 19, 9, tzinfo=UTC)


def not_found() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://r5/route")
    return httpx.HTTPStatusError(
        "404", request=request, response=httpx.Response(404, request=request)
    )


def result() -> r5_provider.RouteResult:
    return r5_provider.RouteResult(
        legs=[TravelLeg(distance_km=2, duration_min=12, mode=TravelMode.METRO)],
        total_duration_min=15,
        walking_duration_min=1,
        waiting_duration_min=2,
        transit_duration_min=9,
        entry_exit_penalty_min=1,
        reliability_buffer_min=2,
        transfers=0,
    )


@pytest.mark.asyncio
async def test_nearby_access_adds_real_walk_and_shifts_departure():
    walk = TravelLeg(distance_km=0.15, duration_min=2, geometry="shape", mode=TravelMode.WALK)
    with (
        patch.object(r5_access, "_nearby_points", return_value=iter([ORIGIN.model_copy(update={"latitude": 55.699})])),
        patch.object(r5_access, "_walk", AsyncMock(return_value=walk)),
        patch.object(r5_provider, "build_route", AsyncMock(side_effect=[not_found(), result()])) as build,
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert build.await_args_list[1].args[2] == datetime(2026, 9, 19, 9, 2, tzinfo=UTC)
    assert [leg.mode for leg in route.legs] == [TravelMode.WALK, TravelMode.METRO]
    assert route.total_duration_min == 17
    assert route.walking_duration_min == 3


@pytest.mark.asyncio
async def test_no_access_keeps_r5_not_found():
    with (
        patch.object(r5_access, "_walk", AsyncMock(return_value=None)),
        patch.object(r5_provider, "build_route", AsyncMock(side_effect=not_found())) as build,
        pytest.raises(httpx.HTTPStatusError) as error,
    ):
        await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert error.value.response.status_code == 404
    build.assert_awaited_once()


@pytest.mark.asyncio
async def test_matrix_repairs_isolated_point_in_both_directions():
    candidate = ORIGIN.model_copy(update={"latitude": 55.699})
    walk = TravelLeg(distance_km=0.15, duration_min=2, geometry="shape", mode=TravelMode.WALK)
    with (
        patch.object(r5_access, "_nearby_points", return_value=iter([candidate])),
        patch.object(r5_access, "_walk", AsyncMock(return_value=walk)),
        patch.object(
            r5_provider,
            "build_duration_matrix",
            AsyncMock(return_value=[[0, 18], [19, 0]]),
        ) as build,
    ):
        repaired = await r5_access.repair_duration_matrix(
            [ORIGIN, DESTINATION], DEPARTURE, [[0, None], [None, 0]]
        )

    assert repaired == [[0, 20], [21, 0]]
    build.assert_awaited_once_with([candidate, DESTINATION], DEPARTURE)


@pytest.mark.asyncio
async def test_matrix_preserves_existing_connections():
    with patch.object(r5_provider, "build_duration_matrix", AsyncMock()) as build:
        repaired = await r5_access.repair_duration_matrix(
            [ORIGIN, DESTINATION], DEPARTURE, [[0, 10], [None, 0]]
        )

    assert repaired == [[0, 10], [None, 0]]
    build.assert_not_awaited()
