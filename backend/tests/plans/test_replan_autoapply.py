"""Пересчёт вступает в силу сам — в момент, на который посчитан (docs/algoV2.md, шаг 6).

Проверяем развилку: момент настал и всё по плану — пересчёт заменяет прежний план; появились
новые вводные — он помечается недействительным с причиной, и бригады остаются на прежнем плане.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.planner import planning_service, replan_autoapply

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 17, 12, 10, tzinfo=MSK)


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
            replan_autoapply.plans_repository,
            "due_replans",
            AsyncMock(side_effect=[due, []] if due else [[]]),
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
