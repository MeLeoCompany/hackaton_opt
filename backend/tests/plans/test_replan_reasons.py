"""Повод пересчитать утверждённый план: снятые заявки и новые заявки дня."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.planner import planning_service

NEW, PLANNED = RequestStatusId.NEW, RequestStatusId.PLANNED


def plan(approved: bool = True):
    return SimpleNamespace(
        id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        approved_at=datetime(2026, 8, 16, 18, tzinfo=UTC) if approved else None,
    )


def request(request_id, status_id, approved_plan_id=None, priority_id=1):
    return SimpleNamespace(
        id=request_id,
        status_id=status_id,
        approved_plan_id=approved_plan_id,
        priority_id=priority_id,
    )


async def reasons(the_plan, *, withdrawn, day_requests, seen):
    plans_repository = planning_service.plans_repository
    with (
        patch.object(
            plans_repository, "list_withdrawn_requests", AsyncMock(return_value=withdrawn)
        ),
        patch.object(plans_repository, "plan_request_ids", AsyncMock(return_value=seen)),
        patch.object(planning_service, "plan_route_delays", AsyncMock(return_value={})),
        patch.object(
            planning_service.references_repository,
            "list_priorities",
            AsyncMock(
                return_value=[SimpleNamespace(id=2, level=1), SimpleNamespace(id=1, level=3)]
            ),
        ),
        patch.object(
            planning_service.requests_repository,
            "list_active_requests_in_period",
            AsyncMock(return_value=day_requests),
        ),
    ):
        return await planning_service.replan_reasons(object(), the_plan)


@pytest.mark.asyncio
async def test_new_request_of_the_day_is_a_reason_to_replan():
    result = await reasons(
        plan(),
        withdrawn=[],
        day_requests=[request(1, PLANNED, 22), request(7, NEW), request(8, NEW, priority_id=2)],
        seen={1},
    )

    assert result["new_request_ids"] == [7, 8]
    # новая авария — отдельным поводом: она меняет маршруты бригад посреди дня
    assert result["urgent_request_ids"] == [8]


@pytest.mark.asyncio
async def test_request_the_plan_already_saw_is_not_new():
    # заявку не удалось назначить при расчёте или её сняли с плана — она не «новая»
    result = await reasons(
        plan(),
        withdrawn=[(5, NEW)],
        day_requests=[request(5, NEW), request(6, NEW)],
        seen={5, 6},
    )

    assert [item.model_dump() for item in result["withdrawn_requests"]] == [
        {"request_id": 5, "status_id": NEW}
    ]
    assert result["new_request_ids"] == []


@pytest.mark.asyncio
async def test_plan_that_is_not_approved_has_nothing_to_replan():
    assert await planning_service.replan_reasons(object(), plan(approved=False)) == {}
