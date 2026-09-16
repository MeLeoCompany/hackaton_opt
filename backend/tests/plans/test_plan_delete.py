"""Удаление плана: день можно пересчитать заново."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service
from src.services.planner.planning_service import PlanNotFoundError


@pytest.mark.asyncio
async def test_plan_is_deleted_and_committed():
    plan = SimpleNamespace(id=9)
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with patch.object(repository, 'get_plan', AsyncMock(return_value=plan)), \
         patch.object(repository, 'delete_plan', AsyncMock()) as delete_plan:
        await planning_service.delete_plan(session, 9)

    delete_plan.assert_awaited_once_with(session, plan)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleting_missing_plan_is_not_found():
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with patch.object(repository, 'get_plan', AsyncMock(return_value=None)):
        with pytest.raises(PlanNotFoundError):
            await planning_service.delete_plan(session, 99)

    session.commit.assert_not_awaited()
