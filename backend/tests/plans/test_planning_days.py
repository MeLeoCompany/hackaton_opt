from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.planner import planning_service

PLANNED = RequestStatusId.PLANNED


@pytest.mark.asyncio
async def test_planning_days_include_every_day_touched_by_request_window():
    requests = [
        SimpleNamespace(
            status_id=PLANNED,
            window_start=datetime.fromisoformat("2026-08-17T23:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T02:00:00+03:00"),
        ),
        SimpleNamespace(
            status_id=PLANNED,
            window_start=datetime.fromisoformat("2026-08-18T10:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T11:00:00+03:00"),
        ),
    ]
    with patch.object(
        planning_service.requests_repository,
        "list_active_requests",
        AsyncMock(return_value=requests),
    ):
        days = await planning_service.list_planning_days(SimpleNamespace(), office_id=1)

    assert [(str(day.plan_date), day.active_requests) for day in days] == [
        ("2026-08-17", 1),
        ("2026-08-18", 2),
    ]


@pytest.mark.asyncio
async def test_window_ending_at_midnight_does_not_add_empty_next_day():
    requests = [
        SimpleNamespace(
            status_id=PLANNED,
            window_start=datetime.fromisoformat("2026-08-17T22:00:00+03:00"),
            window_end=datetime.fromisoformat("2026-08-18T00:00:00+03:00"),
        )
    ]
    with patch.object(
        planning_service.requests_repository,
        "list_active_requests",
        AsyncMock(return_value=requests),
    ):
        days = await planning_service.list_planning_days(SimpleNamespace(), office_id=1)

    assert [(str(day.plan_date), day.active_requests) for day in days] == [("2026-08-17", 1)]


@pytest.mark.asyncio
async def test_new_request_with_closed_window_is_overdue():
    """Хвост прошедшего дня: «Новая», а окно уже закрылось — день пересчитать нельзя."""

    def request(status, start, end):
        return SimpleNamespace(
            status_id=status,
            window_start=datetime.fromisoformat(start),
            window_end=datetime.fromisoformat(end),
        )

    requests = [
        request(RequestStatusId.NEW, "2026-08-17T10:00:00+03:00", "2026-08-17T12:00:00+03:00"),
        # «В плане» с закрытым окном — за ней следит план дня, это не хвост
        request(PLANNED, "2026-08-17T10:00:00+03:00", "2026-08-17T12:00:00+03:00"),
        # окно ещё открыто
        request(RequestStatusId.NEW, "2026-08-17T15:00:00+03:00", "2026-08-17T18:00:00+03:00"),
    ]
    with (
        patch.object(
            planning_service.requests_repository,
            "list_active_requests",
            AsyncMock(return_value=requests),
        ),
        patch.object(
            planning_service.clock,
            "now",
            return_value=datetime.fromisoformat("2026-08-17T14:00:00+03:00"),
        ),
    ):
        [day] = await planning_service.list_planning_days(SimpleNamespace(), office_id=1)

    assert (day.active_requests, day.overdue_requests) == (3, 1)
