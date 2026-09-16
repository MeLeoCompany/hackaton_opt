from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service


@pytest.mark.asyncio
async def test_planning_days_include_every_day_touched_by_request_window():
    requests = [
        SimpleNamespace(
            window_start=datetime.fromisoformat("2026-08-17T23:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T02:00:00+03:00"),
        ),
        SimpleNamespace(
            window_start=datetime.fromisoformat("2026-08-18T10:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T11:00:00+03:00"),
        ),
    ]
    with patch.object(
        planning_service.requests_repository,
        "list_active_requests",
        AsyncMock(return_value=requests),
    ):
        days = await planning_service.list_planning_days(SimpleNamespace())

    assert [(str(day.plan_date), day.active_requests) for day in days] == [
        ("2026-08-17", 1),
        ("2026-08-18", 2),
    ]


@pytest.mark.asyncio
async def test_window_ending_at_midnight_does_not_add_empty_next_day():
    requests = [
        SimpleNamespace(
            window_start=datetime.fromisoformat("2026-08-17T22:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T00:00:00+03:00"),
        )
    ]
    with patch.object(
        planning_service.requests_repository,
        "list_active_requests",
        AsyncMock(return_value=requests),
    ):
        days = await planning_service.list_planning_days(SimpleNamespace())

    assert [(str(day.plan_date), day.active_requests) for day in days] == [("2026-08-17", 1)]
