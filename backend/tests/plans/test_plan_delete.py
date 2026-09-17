"""Удаление плана: день можно пересчитать заново; утверждённый план так просто не удалить."""

from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service
from src.services.planner.planning_service import PlanNotFoundError


@pytest.mark.asyncio
async def test_plan_is_deleted_and_committed():
    plan = SimpleNamespace(id=9, approved_at=None)
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan)),
        patch.object(repository, "delete_plan", AsyncMock()) as delete_plan,
    ):
        await planning_service.delete_plan(session, 9)

    delete_plan.assert_awaited_once_with(session, plan)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleting_missing_plan_is_not_found():
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=None)),
        pytest.raises(PlanNotFoundError),
    ):
        await planning_service.delete_plan(session, 99)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_plan_is_not_deleted():
    """Иначе заявки остались бы закреплёнными за несуществующим планом."""
    from datetime import datetime

    from src.services.planner.planning_service import PlanInUseError

    plan = SimpleNamespace(id=9, approved_at=datetime(2026, 8, 17, tzinfo=UTC))
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan)),
        patch.object(repository, "delete_plan", AsyncMock()) as delete_plan,
        pytest.raises(PlanInUseError, match="утверждён"),
    ):
        await planning_service.delete_plan(session, 9)

    delete_plan.assert_not_awaited()
    session.commit.assert_not_awaited()
