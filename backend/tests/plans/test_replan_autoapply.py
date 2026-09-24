"""Пересчёт вступает в силу сам — в момент, на который посчитан (docs/algoV2.md, шаг 6).

Проверяем развилку: момент настал и всё по плану — пересчёт заменяет прежний план; появились
новые вводные — он помечается недействительным с причиной, и бригады остаются на прежнем плане.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.planner import planning_service, replan_autoapply

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 17, 12, 10, tzinfo=MSK)
DAY = NOW.date()


class FakeSession:
    """Сессия на время проверки: считаем коммиты и откаты."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def replan(plan_id=30):
    return SimpleNamespace(id=plan_id, voided_at=None, void_reason=None)


def run(session, due, approve):
    with (
        patch.object(replan_autoapply, "async_session_maker", lambda: session),
        patch.object(
            replan_autoapply.plans_repository, "due_replans", AsyncMock(return_value=due)
        ),
        patch.object(replan_autoapply.planning_service, "approve_replan", approve),
        patch.object(replan_autoapply.clock, "now", return_value=NOW),
    ):
        return asyncio.run(replan_autoapply.apply_due())


def test_replan_takes_effect_when_its_moment_comes():
    session, plan = FakeSession(), replan()

    applied = run(session, [plan], AsyncMock())

    assert applied == [plan.id]
    assert plan.voided_at is None


def test_replan_with_new_facts_does_not_take_effect():
    session, plan = FakeSession(), replan()
    refusal = planning_service.PlanInUseError(
        "Пересчёт №30 не вступил в силу: пока шли расчёт и обзвон, появились заявки №96"
    )

    applied = run(session, [plan], AsyncMock(side_effect=refusal))

    assert applied == []
    assert plan.voided_at == NOW
    assert "появились заявки №96" in plan.void_reason
    # расчёт откатывается целиком, а пометка сохраняется
    assert (session.rollbacks, session.commits) == (1, 1)


def test_nothing_happens_until_the_moment_comes():
    session = FakeSession()

    assert run(session, [], AsyncMock()) == []
    assert (session.rollbacks, session.commits) == (0, 0)


@pytest.mark.asyncio
async def test_approved_replan_retires_its_siblings():
    """Утвердили один пересчёт — остальные считались от плана, которого больше нет."""
    parent = SimpleNamespace(id=311)
    chosen = SimpleNamespace(id=313)
    sibling = SimpleNamespace(id=314, voided_at=None, void_reason=None)

    with patch.object(
        planning_service.plans_repository,
        "pending_replans",
        AsyncMock(return_value=[chosen, sibling]),
    ):
        retired = await planning_service.retire_sibling_replans(object(), parent, chosen, NOW)

    assert retired == [314]
    assert sibling.voided_at == NOW
    assert "№313" in sibling.void_reason


@pytest.mark.asyncio
async def test_empty_day_snapshot_still_guards_against_new_requests():
    """Пустой снимок — это день без заявок к раскладке, а не «снимка нет».

    Раньше такой пересчёт проскакивал проверку и вступал в силу, хотя заявка уже пришла.
    """
    parent = SimpleNamespace(id=313, plan_date=DAY, office_id=1, superseded_at=None)
    plan = SimpleNamespace(
        id=315,
        parent_plan_id=313,
        plan_date=DAY,
        office_id=1,
        replanned_at=NOW,
        input_snapshot={"day_requests": [], "request_order": []},
    )
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(
            planning_service.day_state,
            "new_since",
            AsyncMock(return_value=["появились заявки №13"]),
        ),
        patch.object(planning_service.clock, "now", return_value=NOW),
        pytest.raises(planning_service.PlanInUseError, match="№13"),
    ):
        await planning_service.approve_replan(object(), plan)
