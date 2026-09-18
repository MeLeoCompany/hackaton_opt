"""Утверждение плана: заявки закрепляются за днём и другим дням не достаются."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.schemas.plans import PlanSummary
from src.services.planner import planning_service
from src.services.planner.planning_service import PlanDataError, PlanInUseError

# офис диспетчера, от имени которого идут вызовы
OFFICE = 1


def plan(plan_id, approved_at=None, plan_date=date(2026, 8, 17)):
    return SimpleNamespace(
        id=plan_id, plan_date=plan_date, approved_at=approved_at, office_id=OFFICE
    )


def summary(plan_id):
    return PlanSummary(
        id=plan_id,
        run_type="optimized",
        plan_date=date(2026, 8, 17),
        solver="cuopt",
        created_at=datetime(2026, 8, 17, 7, tzinfo=UTC),
        engineers_used=2,
        assigned_count=3,
        unassigned_count=0,
    )


@pytest.mark.asyncio
async def test_approval_holds_plan_requests():
    target = plan(9)
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(3, 3))) as hold,
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=[summary(9)])),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    assert hold.await_args.args[1] is target
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_plan_cannot_steal_requests_held_by_another_plan():
    target = plan(9)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(2, 3))),
        pytest.raises(PlanInUseError, match="устарел"),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_approval_is_reported_as_conflict():
    target = plan(9)
    session = SimpleNamespace(
        commit=AsyncMock(side_effect=IntegrityError("unique", {}, Exception())),
        rollback=AsyncMock(),
    )
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(3, 3))),
        pytest.raises(PlanInUseError, match="одновременно"),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_plan_without_date_cannot_be_approved():
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan(9, plan_date=None))),
        patch.object(repository, "hold_plan_requests", AsyncMock()) as hold,
        pytest.raises(PlanDataError, match="не может быть утверждён"),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    hold.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_plan_of_the_day_is_not_approved():
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan(9))),
        patch.object(
            repository, "get_approved_plan", AsyncMock(return_value=plan(8, datetime.now(UTC)))
        ),
        patch.object(repository, "hold_plan_requests", AsyncMock()) as hold,
        pytest.raises(PlanInUseError, match="№8"),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    hold.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelling_approval_releases_requests():
    target = plan(9, datetime.now(UTC))
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "release_plan_requests", AsyncMock(return_value=3)) as release,
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=[summary(9)])),
    ):
        await planning_service.cancel_plan_approval(session, 9, office_id=OFFICE)

    release.assert_awaited_once_with(session, target)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_day_check_reports_requests_held_by_another_day():
    """Из этого интерфейс делает предупреждение: часть заявок в расчёт не попадёт."""
    held_request = SimpleNamespace(
        id=42,
        address="Ленина, 1",
        window_start=datetime(2026, 8, 17, 20, tzinfo=UTC),
        window_end=datetime(2026, 8, 17, 23, tzinfo=UTC),
    )
    requests_repository = planning_service.requests_repository

    with (
        patch.object(
            requests_repository, "list_active_requests_in_period", AsyncMock(return_value=[1, 2])
        ),
        patch.object(
            requests_repository,
            "list_requests_held_by_other_days",
            AsyncMock(return_value=[(held_request, plan(8, plan_date=date(2026, 8, 16)))]),
        ),
        patch.object(
            planning_service.plans_repository, "get_approved_plan", AsyncMock(return_value=None)
        ),
    ):
        check = await planning_service.check_planning_day(
            AsyncMock(), date(2026, 8, 17), office_id=OFFICE
        )

    assert check.active_requests == 2
    assert check.approved_plan_id is None
    [held] = check.held_requests
    assert (held.request_id, held.plan_id, held.plan_date) == (42, 8, date(2026, 8, 16))
