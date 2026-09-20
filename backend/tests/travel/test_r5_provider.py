from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import pytest

from src.schemas.travel import Point
from src.services.travel import r5_provider


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


POINTS = [
    Point(latitude=55.78, longitude=37.68),
    Point(latitude=55.69, longitude=37.53),
]
DEPARTURE = datetime(2026, 9, 18, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_build_duration_matrix_preserves_null_and_converts_seconds_to_minutes():
    post = AsyncMock(
        return_value=FakeResponse(
            {
                "point_ids": ["point-0", "point-1"],
                "durations_seconds": [[0, 660], [None, 0]],
            }
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post

    with patch.object(r5_provider.httpx, "AsyncClient", return_value=client):
        result = await r5_provider.build_duration_matrix(POINTS, DEPARTURE)

    assert result == [[0, 11], [None, 0]]
    payload = post.await_args.kwargs["json"]
    assert payload["departure_time"] == "2026-09-18T09:00:00+00:00"
    assert payload["points"] == [
        {"id": "point-0", "lat": 55.78, "lon": 37.68},
        {"id": "point-1", "lat": 55.69, "lon": 37.53},
    ]


@pytest.mark.asyncio
async def test_build_duration_matrix_rejects_changed_point_order():
    response = FakeResponse(
        {
            "point_ids": ["point-1", "point-0"],
            "durations_seconds": [[0, 600], [600, 0]],
        }
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=response)

    with (
        patch.object(r5_provider.httpx, "AsyncClient", return_value=client),
        pytest.raises(ValueError, match="порядок"),
    ):
        await r5_provider.build_duration_matrix(POINTS, DEPARTURE)


@pytest.mark.asyncio
async def test_build_duration_matrix_requires_timezone():
    with pytest.raises(ValueError, match="часовым поясом"):
        await r5_provider.build_duration_matrix(POINTS, DEPARTURE.replace(tzinfo=None))


@pytest.mark.asyncio
async def test_large_matrix_is_assembled_from_rectangular_blocks():
    points = [Point(latitude=55.7 + index * 0.01, longitude=37.6) for index in range(5)]

    async def post(path, *, json):
        assert path == "/matrix-block"
        origins = [point["id"] for point in json["origins"]]
        destinations = [point["id"] for point in json["destinations"]]
        assert len(origins) * len(destinations) <= 4
        values = [
            [
                None
                if (origin, destination) == ("point-2", "point-4")
                else 0
                if origin == destination
                else 60 * (10 * int(origin[6:]) + int(destination[6:]))
                for destination in destinations
            ]
            for origin in origins
        ]
        return FakeResponse(
            {"origin_ids": origins, "destination_ids": destinations, "durations_seconds": values}
        )

    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(side_effect=post)
    with (
        patch.object(r5_provider.httpx, "AsyncClient", return_value=client),
        patch.object(r5_provider.settings, "r5_matrix_single_max_points", 2),
        patch.object(r5_provider.settings, "r5_matrix_block_origins", 2),
        patch.object(r5_provider.settings, "r5_matrix_block_max_pairs", 4),
    ):
        result = await r5_provider.build_duration_matrix(points, DEPARTURE)

    assert result[0] == [0, 1, 2, 3, 4]
    assert result[2] == [20, 21, 0, 23, None]
    assert result[4] == [40, 41, 42, 43, 0]
    assert client.__aenter__.return_value.post.await_count == 8


@pytest.mark.asyncio
async def test_large_matrix_rejects_incorrect_block_ids():
    points = [*POINTS, Point(latitude=55.75, longitude=37.65)]
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(
        return_value=FakeResponse(
            {
                "origin_ids": ["wrong"],
                "destination_ids": ["point-0"],
                "durations_seconds": [[0]],
            }
        )
    )
    with (
        patch.object(r5_provider.httpx, "AsyncClient", return_value=client),
        patch.object(r5_provider.settings, "r5_matrix_single_max_points", 2),
        patch.object(r5_provider.settings, "r5_matrix_block_origins", 1),
        patch.object(r5_provider.settings, "r5_matrix_block_max_pairs", 1),
        pytest.raises(ValueError, match="порядок"),
    ):
        await r5_provider.build_duration_matrix(points, DEPARTURE)


@pytest.mark.asyncio
async def test_build_route_converts_r5_legs_and_geometry():
    post = AsyncMock(
        return_value=FakeResponse(
            {
                "total_duration_seconds": 900,
                "walking_duration_seconds": 180,
                "waiting_duration_seconds": 120,
                "transit_duration_seconds": 480,
                "entry_exit_penalty_seconds": 60,
                "reliability_buffer_seconds": 60,
                "transfers": 1,
                "legs": [
                    {
                        "mode": "walk",
                        "duration_seconds": 180,
                        "wait_seconds": 0,
                        "distance_meters": 200,
                        "route_id": None,
                        "from_stop_id": None,
                        "to_stop_id": "stop-a",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[37.68, 55.78], [37.681, 55.781]],
                        },
                    },
                    {
                        "mode": "subway",
                        "duration_seconds": 480,
                        "wait_seconds": 120,
                        "distance_meters": None,
                        "route_id": "metro-1",
                        "from_stop_id": "stop-a",
                        "to_stop_id": "stop-b",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[37.681, 55.781], [37.53, 55.69]],
                        },
                    },
                ],
            }
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post

    with (
        patch.object(r5_provider.httpx, "AsyncClient", return_value=client),
        patch.object(r5_provider, "_color_for_route", return_value="#E42313"),
        patch.object(r5_provider, "_name_for_route", return_value="1"),
    ):
        result = await r5_provider.build_route(POINTS[0], POINTS[1], DEPARTURE)

    assert [leg.mode.value for leg in result.legs] == ["walk", "metro"]
    assert result.legs[1].route_id == "metro-1"
    assert result.legs[1].route_short_name == "1"
    assert result.legs[1].route_color == "#E42313"
    assert result.legs[1].wait_min == 2
    assert result.legs[1].distance_km > 0
    assert all(leg.geometry for leg in result.legs)
    assert result.total_duration_min == 15
    assert result.transfers == 1
    assert post.await_args.kwargs["json"]["origin"] == {"lat": 55.78, "lon": 37.68}


def test_parse_route_rejects_negative_duration():
    with pytest.raises(ValueError, match="duration_seconds"):
        r5_provider._parse_route(
            {
                "legs": [
                    {
                        "mode": "bus",
                        "duration_seconds": -1,
                        "wait_seconds": 0,
                        "distance_meters": 1,
                    }
                ]
            }
        )


def test_route_colors_come_from_gtfs_and_reject_invalid_values(tmp_path):
    archive_path = tmp_path / "feed.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "routes.txt",
            "route_id,route_color,route_short_name\n"
            "metro-1,e42313,1\nbus-1,0072BA,н1\nbad,red;alert(1),\n",
        )

    with patch.object(r5_provider.settings, "r5_gtfs_path", archive_path):
        assert r5_provider._color_for_route("metro-1") == "#E42313"
        assert r5_provider._color_for_route("bus-1") == "#0072BA"
        assert r5_provider._color_for_route("bad") is None
        assert r5_provider._name_for_route("bus-1") == "н1"
