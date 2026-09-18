from datetime import datetime, timezone

import pytest
from app.models import MatrixRequest
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
