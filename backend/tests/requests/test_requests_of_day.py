"""Список заявок дня: перенесённые с него остаются видны, в слепок дня не попадают."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.requests import requests_service

MSK = timezone(timedelta(hours=3))
DAY = date(2026, 8, 19)


def request_row(request_id, start_day, moved_from=None):
    return SimpleNamespace(
        id=request_id,
        window_start=datetime(start_day.year, start_day.month, start_day.day, 14, tzinfo=MSK),
        moved_from=moved_from,
    )


async def listed(**kwargs):
    own = request_row(10, DAY)
    moved = request_row(22, date(2026, 8, 20), moved_from=DAY)
    repository = requests_service.requests_repository
    with (
        patch.object(repository, "list_requests_in_period", AsyncMock(return_value=[own])),
        patch.object(repository, "list_requests_moved_from", AsyncMock(return_value=[moved])),
    ):
        return await requests_service.list_requests(object(), 1, DAY, **kwargs)


@pytest.mark.asyncio
async def test_moved_request_stays_in_the_day_it_left():
    assert [request.id for request in await listed()] == [10, 22]


@pytest.mark.asyncio
async def test_day_snapshot_keeps_only_requests_of_this_day():
    assert [request.id for request in await listed(with_moved_out=False)] == [10]
