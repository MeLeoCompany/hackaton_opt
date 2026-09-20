from datetime import datetime, timezone

import pytest
from app.models import MatrixBlockRequest, MatrixRequest
from pydantic import ValidationError


def test_matrix_rejects_duplicate_point_ids() -> None:
    with pytest.raises(ValidationError, match="должны быть уникальными"):
        MatrixRequest(
            points=[
                {"id": "same", "lat": 55.7, "lon": 37.6},
                {"id": "same", "lat": 55.8, "lon": 37.7},
            ],
            departure_time=datetime(2026, 9, 18, 9, tzinfo=timezone.utc),
        )


def test_matrix_requires_departure_timezone() -> None:
    with pytest.raises(ValidationError, match="должен содержать часовой пояс"):
        MatrixRequest(
            points=[
                {"id": "a", "lat": 55.7, "lon": 37.6},
                {"id": "b", "lat": 55.8, "lon": 37.7},
            ],
            departure_time=datetime(2026, 9, 18, 9, tzinfo=timezone.utc).replace(
                tzinfo=None
            ),
        )


def test_block_allows_same_id_across_lists_but_rejects_duplicates_within_list() -> None:
    departure = datetime(2026, 9, 18, 9, tzinfo=timezone.utc)
    MatrixBlockRequest(
        origins=[{"id": "a", "lat": 55.7, "lon": 37.6}],
        destinations=[{"id": "a", "lat": 55.7, "lon": 37.6}],
        departure_time=departure,
    )
    with pytest.raises(ValidationError, match="должны быть уникальными"):
        MatrixBlockRequest(
            origins=[{"id": "a", "lat": 55.7, "lon": 37.6}] * 2,
            destinations=[{"id": "b", "lat": 55.8, "lon": 37.7}],
            departure_time=departure,
        )
