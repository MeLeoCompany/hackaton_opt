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


@pytest.mark.asyncio
async def test_stale_replan_is_retired_without_waiting_for_its_moment():
    """День изменился — ждать момента незачем: пока пересчёт висит, бригадам закрыт выезд."""
    fresh = SimpleNamespace(id=321, parent_plan_id=318, voided_at=None, void_reason=None)
    stale = SimpleNamespace(id=322, parent_plan_id=319, voided_at=None, void_reason=None)
    session = FakeSession()
    reasons = {321: None, 322: "Пересчёт №322 не вступит в силу: появились заявки №13"}

    with (
        patch.object(replan_autoapply, "async_session_maker", lambda: session),
        patch.object(
            replan_autoapply.plans_repository,
            "waiting_replans",
            AsyncMock(return_value=[fresh, stale]),
        ),
        patch.object(
            replan_autoapply.planning_service,
            "replan_stale_reason",
            AsyncMock(side_effect=lambda _s, plan: reasons[plan.id]),
        ),
        patch.object(replan_autoapply.clock, "now", return_value=NOW),
    ):
        voided = await replan_autoapply.void_stale()

    assert voided == [322]
    assert fresh.voided_at is None
    assert (stale.voided_at, "№13" in stale.void_reason) == (NOW, True)
    assert session.commits == 1


@pytest.mark.asyncio
async def test_only_the_last_replan_of_a_plan_keeps_waiting():
    """Пересчитали дважды — ждёт последний, прежний отзываем, не дожидаясь его момента."""
    previous = SimpleNamespace(id=324, parent_plan_id=323, voided_at=None, void_reason=None)
    last = SimpleNamespace(id=325, parent_plan_id=323, voided_at=None, void_reason=None)
    session = FakeSession()

    with (
        patch.object(replan_autoapply, "async_session_maker", lambda: session),
        patch.object(
            replan_autoapply.plans_repository,
            "waiting_replans",
            AsyncMock(return_value=[previous, last]),
        ),
        patch.object(
            replan_autoapply.planning_service, "replan_stale_reason", AsyncMock(return_value=None)
        ) as stale,
        patch.object(replan_autoapply.clock, "now", return_value=NOW),
    ):
        voided = await replan_autoapply.void_stale()

    assert voided == [324]
    assert "№325" in previous.void_reason
    assert last.voided_at is None
    # у прежнего день не сверяем: он отозван по более простой причине
    assert stale.await_count == 1


def test_window_search_without_answers_is_not_a_plan_yet():
    """Подбор окон сам в силу не вступает и бригад не держит: сначала ответы клиентов."""
    from src.repositories.plans import plans_repository

    picked = SimpleNamespace(
        id=41, input_snapshot={"widened_requests": [12]}, decisions_count=None
    )
    decided = SimpleNamespace(
        id=42, input_snapshot={"widened_requests": [12]}, decisions_count=1
    )
    ordinary = SimpleNamespace(id=43, input_snapshot={"request_order": [11]}, decisions_count=None)

    assert plans_repository.awaits_answers(picked) is True
    assert plans_repository.awaits_answers(decided) is False
    assert plans_repository.awaits_answers(ordinary) is False
