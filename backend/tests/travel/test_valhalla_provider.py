from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.travel import Point, TransportKind
from src.services.travel import valhalla_provider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_pedestrian_route_strictly_excludes_ferries():
    post = AsyncMock(
        return_value=FakeResponse(
            {
                "trip": {
                    "summary": {"length": 1.0, "time": 600},
                    "legs": [{"shape": "encoded", "summary": {"length": 1.0, "time": 600}}],
                }
            }
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post

    with patch.object(valhalla_provider.httpx, "AsyncClient", return_value=client):
        await valhalla_provider.build_route(
            [Point(latitude=55.75, longitude=37.61), Point(latitude=55.76, longitude=37.62)],
            TransportKind.PEDESTRIAN,
        )

    payload = post.await_args.kwargs["json"]
    assert payload["costing_options"]["pedestrian"] == {
        "use_ferry": 0.0,
        "exclude_ferries": True,
    }


@pytest.mark.asyncio
async def test_pedestrian_matrix_strictly_excludes_ferries():
    post = AsyncMock(
        return_value=FakeResponse(
            {
                "sources_to_targets": [
                    [
                        {"from_index": 0, "to_index": 0, "distance": 0, "time": 0},
                        {"from_index": 0, "to_index": 1, "distance": 1, "time": 600},
                    ],
                    [
                        {"from_index": 1, "to_index": 0, "distance": 1, "time": 600},
                        {"from_index": 1, "to_index": 1, "distance": 0, "time": 0},
                    ],
                ]
            }
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post

    with patch.object(valhalla_provider.httpx, "AsyncClient", return_value=client):
        await valhalla_provider.build_matrix(
            [Point(latitude=55.75, longitude=37.61), Point(latitude=55.76, longitude=37.62)],
            TransportKind.PEDESTRIAN,
        )

    payload = post.await_args.kwargs["json"]
    assert payload["costing_options"]["pedestrian"]["exclude_ferries"] is True


@pytest.mark.asyncio
async def test_car_route_does_not_receive_pedestrian_options():
    post = AsyncMock(
        return_value=FakeResponse(
            {
                "trip": {
                    "summary": {"length": 1.0, "time": 600},
                    "legs": [{"shape": "encoded", "summary": {"length": 1.0, "time": 600}}],
                }
            }
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post

    with patch.object(valhalla_provider.httpx, "AsyncClient", return_value=client):
        await valhalla_provider.build_route(
            [Point(latitude=55.75, longitude=37.61), Point(latitude=55.76, longitude=37.62)],
            TransportKind.CAR,
        )

    assert "costing_options" not in post.await_args.kwargs["json"]
