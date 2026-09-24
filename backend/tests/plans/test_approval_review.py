"""Перед утверждением черновика: окна для невлезших заявок и новый расчёт после решений."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.schemas.plans import ReplanDecision, SolverName
from src.services.planner import approval_review
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion
from src.services.planner.planning_service import PlanDataError, PlanInUseError
from src.services.planner.window_suggestions import WindowSuggestion

MSK = timezone(timedelta(hours=3))
DAY = date(2026, 8, 17)


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


def draft(solver="cuopt", objective_policy=None):
    return SimpleNamespace(
        id=40,
        plan_date=DAY,
        approved_at=None,
        parent_plan_id=None,
        solver=solver,
        objective_policy=objective_policy,
        input_snapshot={"request_order": [11, 12, 13]},
    )


def unassigned(request_id, status=RequestStatusId.NEW, approved_plan_id=None):
    return SimpleNamespace(
        request_id=request_id,
        engineer_id=None,
        unassigned_reason="окно слишком узкое",
        request=SimpleNamespace(
            address=f"адрес {request_id}",
            window_start=at(10),
            window_end=at(11),
            status_id=status,
            approved_plan_id=approved_plan_id,
        ),
    )


def assigned(request_id):
    return SimpleNamespace(request_id=request_id, engineer_id=1, request=None)


def patched(plan, assignments, approved=None):
    repository = approval_review.plans_repository
    return (
        patch.object(approval_review.planning_service, "find_plan", AsyncMock(return_value=plan)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=approved)),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=assignments)),
        patch.object(
            repository, "count_assignments_by_plan", AsyncMock(return_value={40: (1, 1, 2)})
        ),
    )


@pytest.mark.asyncio
async def test_preview_offers_time_for_requests_that_did_not_fit():
    # №13 за это время успели отменить — звонить по ней уже незачем
    assignments = [
        assigned(11),
        unassigned(12),
        unassigned(13, status=RequestStatusId.CANCELLED),
    ]
    suggestion = WindowSuggestion(request_id=12, start=at(14), engineer_name="Бригада 1")
    find, approved, listed, counted = patched(draft(solver="baseline"), assignments)

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.planning_service, "load_planning_day", AsyncMock()),
        patch.object(
            approval_review.window_suggestions,
            "suggest_windows",
            AsyncMock(return_value={12: suggestion}),
        ) as suggest,
        patch.object(approval_review.clock, "now", return_value=at(9)),
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    # базовый алгоритм ярусов не знает: второй расчёт всегда у cuOpt
    assert suggest.await_args.args[1] is SolverName.CUOPT
    assert suggest.await_args.args[3] == {12}
    assert preview.assigned_count == 1
    [problem] = preview.unassigned
    assert (problem.request_id, problem.suggested_engineer) == (12, "Бригада 1")
    assert problem.suggested_start == at(14)
    assert problem.suggested_end == at(14) + timedelta(minutes=preview.promise_tolerance_minutes)
    assert problem.expired is False


@pytest.mark.asyncio
async def test_preview_without_unassigned_does_not_solve():
    find, approved, listed, counted = patched(draft(), [assigned(11)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.window_suggestions, "suggest_windows", AsyncMock()) as suggest,
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    suggest.assert_not_awaited()
    assert preview.unassigned == []


@pytest.mark.asyncio
async def test_day_with_approved_plan_is_not_reviewed():
    find, approved, listed, counted = patched(draft(), [], approved=SimpleNamespace(id=39))

    with find, approved, listed, counted, pytest.raises(PlanInUseError, match="№39"):
        await approval_review.preview_approval(object(), 40, office_id=1)


@pytest.mark.asyncio
async def test_decisions_only_about_requests_that_did_not_fit():
    find, approved, listed, counted = patched(draft(), [assigned(11), unassigned(12)])
    decisions = [ReplanDecision(request_id=11, action="cancel", reason="не нужна")]

    with find, approved, listed, counted, pytest.raises(PlanDataError) as error:
        await approval_review.decide_approval(object(), 40, decisions, office_id=1)

    assert "№11" in error.value.messages[0]


@pytest.mark.asyncio
async def test_decisions_rebuild_the_day_as_a_new_draft():
    source = draft(
        solver="cuopt",
        objective_policy={
            "criteria": [
                ObjectiveCriterion.URGENT_REQUESTS.value,
                ObjectiveCriterion.TRAVEL_DISTANCE.value,
                ObjectiveCriterion.ASSIGNED_REQUESTS.value,
                ObjectiveCriterion.ENGINEERS_USED.value,
            ]
        },
    )
    new_plan = SimpleNamespace(id=41, decisions_from_plan_id=None, decisions_count=None)
    session = SimpleNamespace(commit=AsyncMock())
    decisions = [
        ReplanDecision(request_id=12, action="agree", window_start=at(14), window_end=at(14, 30))
    ]
    find, approved, listed, counted = patched(source, [unassigned(12)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.replan_service, "apply_decisions", AsyncMock()) as apply,
        patch.object(
            approval_review.planning_service,
            "build_inside_run",
            AsyncMock(return_value=new_plan),
        ) as build,
        patch.object(
            approval_review.planning_service,
            "summarize_plans",
            AsyncMock(return_value=["сводка"]),
        ),
    ):
        summary = await approval_review.decide_approval(
            session, 40, decisions, office_id=1, user_id=5
        )

    assert summary == "сводка"
    assert apply.await_args.args[1] is source
    assert apply.await_args.kwargs["occasion"] == "при утверждении"
    # день считается тем же решателем и с той же целью, что и черновик
    solver, objective_order = build.await_args.args[2:4]
    assert solver is SolverName.CUOPT
    assert objective_order[1] is ObjectiveCriterion.TRAVEL_DISTANCE
    assert (new_plan.decisions_from_plan_id, new_plan.decisions_count) == (40, 1)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_baseline_draft_is_rebuilt_by_baseline():
    """Согласие на окно добавляет работу — тогда считаем заново, тем же решателем."""
    new_plan = SimpleNamespace(id=41)
    session = SimpleNamespace(commit=AsyncMock())
    window = datetime(2026, 8, 17, 17, 40, tzinfo=timezone(timedelta(hours=3)))
    decisions = [
        ReplanDecision(
            request_id=12,
            action="agree",
            window_start=window,
            window_end=window + timedelta(minutes=30),
        )
    ]
    find, approved, listed, counted = patched(draft(solver="baseline"), [unassigned(12)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.replan_service, "apply_decisions", AsyncMock()),
        patch.object(
            approval_review.planning_service,
            "build_inside_run",
            AsyncMock(return_value=new_plan),
        ) as build,
        patch.object(approval_review.planning_service, "summarize_plans", AsyncMock()),
    ):
        await approval_review.decide_approval(session, 40, decisions, office_id=1)

    assert build.await_args.args[2] is SolverName.BASELINE
    assert tuple(build.await_args.args[3]) == tuple(DEFAULT_OBJECTIVE_ORDER)


@pytest.mark.asyncio
async def test_moved_and_cancelled_requests_do_not_start_a_recalculation():
    """Перенос и отмена только убирают работу: маршруты те же, считать нечего."""
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    plan = draft(solver="cuopt")
    decisions = [
        ReplanDecision(request_id=12, action="no_answer"),
        ReplanDecision(request_id=13, action="cancel"),
    ]
    find, approved, listed, counted = patched(plan, [unassigned(12), unassigned(13)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.replan_service, "apply_decisions", AsyncMock()),
        patch.object(
            approval_review.planning_service, "build_inside_run", AsyncMock()
        ) as build,
        patch.object(
            approval_review.plans_repository, "delete_assignments", AsyncMock(return_value=2)
        ) as dropped,
        patch.object(
            approval_review.planning_service,
            "summarize_plans",
            AsyncMock(return_value=["итог"]),
        ),
    ):
        summary = await approval_review.decide_approval(session, 40, decisions, office_id=1)

    assert summary == "итог"
    assert build.await_count == 0  # решателя не звали вовсе
    assert dropped.await_args.args[2] == {12, 13}
    # перенесённых и отменённых в плане больше нет — даже как невлезших
    assert plan.input_snapshot["request_order"] == [11]
