from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
        await r5_provider.build_duration_matrix(
            POINTS, DEPARTURE.replace(tzinfo=None)
        )
