from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import httpx
import pytest

from src.schemas.travel import Point, TravelLeg, TravelMode, TravelProvider
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
async def test_identical_points_need_no_r5_request():
    with patch.object(r5_provider, "build_route", AsyncMock()) as build:
        route = await r5_access.route(ORIGIN, ORIGIN, DEPARTURE)

    assert route.total_duration_min == 0
    assert route.legs == []
    build.assert_not_awaited()


def access_walk(walk):
    def pick(origin, destination, **kwargs):
        return None if origin == ORIGIN and destination == DESTINATION else walk

    return pick


@pytest.mark.asyncio
async def test_direct_walking_wins_when_transit_is_slower():
    walk = TravelLeg(distance_km=0.6, duration_min=8, geometry="shape", mode=TravelMode.WALK)
    with (
        patch.object(r5_access, "_walk", AsyncMock(return_value=walk)),
        patch.object(r5_provider, "build_route", AsyncMock(return_value=result())),
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert route.provider is TravelProvider.VALHALLA
    assert route.total_duration_min == 8
    assert route.legs == [walk]


@pytest.mark.asyncio
async def test_direct_walking_survives_r5_not_found():
    walk = TravelLeg(distance_km=0.6, duration_min=8, geometry="shape", mode=TravelMode.WALK)
    with (
        patch.object(r5_access, "_nearby_stops", return_value=[]),
        patch.object(r5_access, "_nearby_points", return_value=iter([])),
        patch.object(r5_access, "_walk", AsyncMock(return_value=walk)),
        patch.object(r5_provider, "build_route", AsyncMock(side_effect=not_found())),
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert route.provider is TravelProvider.VALHALLA
    assert route.total_duration_min == 8


def test_gtfs_candidates_include_regular_stops_and_skip_parent_station(tmp_path):
    archive_path = tmp_path / "network.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_lat,stop_lon,location_type\n"
            "metro,55.7005,37.5,0\n"
            "bus,55.702,37.5,\n"
            "parent,55.7002,37.5,1\n"
            "far,56.0,37.5,0\n",
        )

    with patch.object(r5_access.settings, "r5_gtfs_path", archive_path):
        candidates = r5_access._nearby_stops(ORIGIN)

    assert [point.latitude for point in candidates] == [55.7005, 55.702]


@pytest.mark.asyncio
async def test_stop_access_selects_fastest_complete_route():
    first = ORIGIN.model_copy(update={"latitude": 55.701})
    second = ORIGIN.model_copy(update={"latitude": 55.702})
    walk = TravelLeg(distance_km=0.2, duration_min=3, geometry="shape", mode=TravelMode.WALK)
    slow = replace(result(), total_duration_min=30)
    fast = replace(result(), total_duration_min=12)
    with (
        patch.object(r5_access, "_nearby_stops", side_effect=[[first, second], []]),
        patch.object(r5_access, "_nearby_points", return_value=iter([])),
        patch.object(r5_access, "_walk", AsyncMock(side_effect=access_walk(walk))),
        patch.object(
            r5_provider, "build_route", AsyncMock(side_effect=[not_found(), slow, fast])
        ) as build,
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert route.total_duration_min == 15
    assert route.walking_duration_min == 4
    assert build.await_args_list[2].args == (
        second,
        DESTINATION,
        datetime(2026, 9, 19, 9, 3, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_stop_access_handles_both_isolated_endpoints():
    first = ORIGIN.model_copy(update={"latitude": 55.701})
    last = DESTINATION.model_copy(update={"latitude": 55.799})
    walk = TravelLeg(distance_km=0.2, duration_min=3, geometry="shape", mode=TravelMode.WALK)

    async def build(start, end, departure):
        if start == first and end == last:
            assert departure == datetime(2026, 9, 19, 9, 3, tzinfo=UTC)
            return result()
        raise not_found()

    with (
        patch.object(r5_access, "_nearby_stops", side_effect=[[first], [last]]),
        patch.object(r5_access, "_nearby_points", return_value=iter([])),
        patch.object(r5_access, "_walk", AsyncMock(side_effect=access_walk(walk))),
        patch.object(r5_provider, "build_route", side_effect=build),
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert route.total_duration_min == 21
    assert [leg.mode for leg in route.legs] == [TravelMode.WALK, TravelMode.METRO, TravelMode.WALK]


@pytest.mark.asyncio
async def test_nearby_access_adds_real_walk_and_shifts_departure():
    walk = TravelLeg(distance_km=0.15, duration_min=2, geometry="shape", mode=TravelMode.WALK)
    with (
        patch.object(r5_access, "_nearby_stops", return_value=[]),
        patch.object(
            r5_access,
            "_nearby_points",
            return_value=iter([ORIGIN.model_copy(update={"latitude": 55.699})]),
        ),
        patch.object(r5_access, "_walk", AsyncMock(side_effect=access_walk(walk))),
        patch.object(
            r5_provider, "build_route", AsyncMock(side_effect=[not_found(), result()])
        ) as build,
    ):
        route = await r5_access.route(ORIGIN, DESTINATION, DEPARTURE)

    assert build.await_args_list[1].args[2] == datetime(2026, 9, 19, 9, 2, tzinfo=UTC)
    assert [leg.mode for leg in route.legs] == [TravelMode.WALK, TravelMode.METRO]
    assert route.total_duration_min == 17
    assert route.walking_duration_min == 3


@pytest.mark.asyncio
async def test_no_access_keeps_r5_not_found():
    with (
        patch.object(r5_access, "_nearby_stops", return_value=[]),
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
