"""Сверка обещаний после расчёта: согласованное время либо держится, либо видно оператору."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service

PLAN = SimpleNamespace(id=45)
PROMISED_FROM = datetime(2026, 8, 17, 14, 40, tzinfo=UTC)
PROMISED_TO = datetime(2026, 8, 17, 15, 10, tzinfo=UTC)


def assignment(engineer_id, planned_start, *, promised=True, request_id=15):
    request = SimpleNamespace(
        id=request_id,
        address="Грайвороновская, 10 к 2",
        promised_from=PROMISED_FROM if promised else None,
        promised_to=PROMISED_TO if promised else None,
    )
    return SimpleNamespace(
        request=request,
        request_id=request_id,
        engineer_id=engineer_id,
        planned_arrival_time=planned_start,
    )


async def check(assignments):
    with patch.object(
        planning_service.plans_repository,
        "list_plan_assignments",
        AsyncMock(return_value=assignments),
    ):
        return await planning_service.broken_promises(object(), PLAN)


@pytest.mark.asyncio
async def test_promise_inside_the_agreed_window_is_kept():
    assert await check([assignment(3, datetime(2026, 8, 17, 14, 55, tzinfo=UTC))]) == []


@pytest.mark.asyncio
async def test_promise_outside_the_window_is_reported():
    broken = await check([assignment(3, datetime(2026, 8, 17, 16, 5, tzinfo=UTC))])

    assert [item.request_id for item in broken] == [15]
    assert broken[0].planned_start == datetime(2026, 8, 17, 16, 5, tzinfo=UTC)


@pytest.mark.asyncio
async def test_promise_dropped_from_the_plan_is_reported():
    broken = await check([assignment(None, None)])

    assert [(item.request_id, item.planned_start) for item in broken] == [(15, None)]


@pytest.mark.asyncio
async def test_requests_without_promise_are_not_checked():
    assert await check([assignment(None, None, promised=False)]) == []
