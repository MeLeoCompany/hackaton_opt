"""Перед утверждением черновика: окна для невлезших заявок и новый расчёт после решений."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.schemas.plans import ReplanDecision, SolverName
from src.services.planner import approval_review
from src.services.planner.planning_service import PlanDataError, PlanInUseError

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
        decisions_count=None,
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


def offered(request_id, start, engineer="Бригада 1"):
    """Заявка, которой подбор окон нашёл время: она стоит в плане вне своего окна."""
    return SimpleNamespace(
        request_id=request_id,
        engineer_id=1,
        planned_arrival_time=start,
        engineer=SimpleNamespace(name=engineer),
        unassigned_reason=None,
        request=SimpleNamespace(
            address=f"адрес {request_id}",
            window_start=at(10),
            window_end=at(11),
            status_id=RequestStatusId.NEW,
            approved_plan_id=None,
            promised_from=None,
        ),
    )


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
async def test_preview_offers_the_time_the_window_search_put_the_request_on():
    """Подбор окон уже разложил день: предложение клиенту — это время из самого расчёта."""
    # №13 за это время успели отменить — звонить по ней уже незачем
    assignments = [
        assigned(11),
        offered(12, at(14)),
        unassigned(13, status=RequestStatusId.CANCELLED),
    ]
    plan = draft()
    plan.input_snapshot = {"request_order": [11, 12, 13], "widened_requests": [12]}
    find, approved, listed, counted = patched(plan, assignments)

    with find, approved, listed, counted, patch.object(
        approval_review.clock, "now", return_value=at(9)
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    assert preview.plan_id == 40
    assert preview.assigned_count == 1
    [problem] = preview.unassigned
    assert (problem.request_id, problem.suggested_engineer) == (12, "Бригада 1")
    assert problem.suggested_start == at(14)
    assert problem.suggested_end == at(14) + timedelta(minutes=preview.promise_tolerance_minutes)
    assert problem.expired is False


@pytest.mark.asyncio
async def test_agreed_request_is_not_asked_about_again():
    """Клиент уже согласился: расчёт ставит заявку в обещанное окно, решать нечего."""
    agreed = offered(12, at(14))
    agreed.request.promised_from = at(14)
    agreed.request.window_start, agreed.request.window_end = at(14), at(14, 30)
    plan = draft()
    plan.input_snapshot = {"request_order": [11, 12], "widened_requests": [12]}
    find, approved, listed, counted = patched(plan, [assigned(11), agreed])

    with find, approved, listed, counted, patch.object(
        approval_review.clock, "now", return_value=at(9)
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    assert preview.unassigned == []


@pytest.mark.asyncio
async def test_preview_never_solves():
    """Расчёт делает подбор окон, а не просмотр решений: открытие окна ничего не считает."""
    find, approved, listed, counted = patched(draft(), [assigned(11)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.planning_service, "build_inside_run", AsyncMock()) as build,
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    build.assert_not_awaited()
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
async def test_agreement_keeps_the_request_where_the_search_put_it():
    """Клиент согласился — день не пересчитываем: расклад уже есть, выпадать некому."""
    plan = draft()
    plan.input_snapshot = {"request_order": [11, 12], "widened_requests": [12]}
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    decisions = [
        ReplanDecision(request_id=12, action="agree", window_start=at(14), window_end=at(14, 30))
    ]
    find, approved, listed, counted = patched(plan, [assigned(11), offered(12, at(14))])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(approval_review.replan_service, "apply_decisions", AsyncMock()) as apply,
        patch.object(approval_review.planning_service, "build_inside_run", AsyncMock()) as build,
        patch.object(
            approval_review.plans_repository, "delete_assignments", AsyncMock()
        ) as dropped,
        patch.object(
            approval_review.planning_service, "summarize_plans", AsyncMock(return_value=["итог"])
        ),
    ):
        summary = await approval_review.decide_approval(
            session, 40, decisions, office_id=1, user_id=5
        )

    assert summary == "итог"
    assert build.await_count == 0  # решателя не звали вовсе
    dropped.assert_not_awaited()  # согласованную из плана не убираем
    assert apply.await_args.kwargs["occasion"] == "при утверждении"
    assert plan.decisions_count == 1


@pytest.mark.asyncio
async def test_window_search_saves_its_own_calculation():
    """«Подобрать окна» — это расчёт дня с раскрытыми окнами, и он сохраняется как план."""
    source = draft(solver="baseline")
    новый = SimpleNamespace(id=41, decisions_from_plan_id=None, decisions_count=None)
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    find, approved, listed, counted = patched(source, [assigned(11), unassigned(12)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(
            approval_review.planning_service,
            "build_inside_run",
            AsyncMock(return_value=новый),
        ) as build,
        patch.object(
            approval_review,
            "preview_approval",
            AsyncMock(return_value="предложения"),
        ) as preview,
        patch.object(
            approval_review.plans_repository, "windows_plan_of", AsyncMock(return_value=None)
        ),
    ):
        result = await approval_review.pick_windows(session, 40, office_id=1, user_id=5)

    assert result == "предложения"
    # базовый алгоритм ярусов не знает: подбор окон считает cuOpt
    assert build.await_args.args[2] is SolverName.CUOPT
    assert build.await_args.kwargs["widen_request_ids"] == {12}
    assert build.await_args.kwargs["fallback_plan_id"] == source.id
    assert новый.decisions_from_plan_id == 40  # в графе дня видно, из чего он вырос
    assert preview.await_args.args[1] == 41
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replan_window_search_keeps_original_calculation_moment():
    """Подбор окон не сдвигает старт пересчёта вперёд, пока оператор смотрит результат."""
    source = replan()
    source.replanned_at = at(12, 15)
    новый = SimpleNamespace(id=42, decisions_from_plan_id=None, decisions_count=None)
    parent = SimpleNamespace(id=40, plan_date=DAY, office_id=1)
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())

    with (
        patch.object(
            approval_review.planning_service, "find_plan", AsyncMock(return_value=source)
        ),
        patch.object(
            approval_review.plans_repository, "get_plan", AsyncMock(return_value=parent)
        ),
        patch.object(
            approval_review.plans_repository, "get_approved_plan", AsyncMock(return_value=parent)
        ),
        patch.object(
            approval_review.planning_service,
            "waiting_unassigned",
            AsyncMock(return_value=[unassigned(12)]),
        ),
        patch.object(
            approval_review.plans_repository, "windows_plan_of", AsyncMock(return_value=None)
        ),
        patch.object(
            approval_review.replan_service,
            "replannable",
            AsyncMock(return_value=(parent, source.replanned_at)),
        ) as replannable,
        patch.object(
            approval_review.replan_service,
            "build_for_approval",
            AsyncMock(return_value=новый),
        ) as build,
        patch.object(
            approval_review.plans_repository,
            "list_plan_assignments",
            AsyncMock(return_value=[assigned(11), unassigned(12)]),
        ),
        patch.object(
            approval_review, "preview_approval", AsyncMock(return_value="предложения")
        ),
    ):
        result = await approval_review.pick_windows(session, 41, office_id=1)

    assert result == "предложения"
    assert replannable.await_args.args[2] == source.replanned_at
    assert build.await_args.kwargs["fallback_plan_id"] == source.id


@pytest.mark.asyncio
async def test_window_search_rejects_newly_displaced_requests():
    """Небезопасный подбор возвращает исходные переносы вместо тупиковой ошибки."""
    source = draft(solver="cuopt")
    новый = SimpleNamespace(id=41, decisions_from_plan_id=None, decisions_count=None)
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), rollback=AsyncMock())
    find, approved, listed, counted = patched(source, [assigned(11), unassigned(12)])
    assignments = AsyncMock(
        side_effect=[
            [assigned(11), unassigned(12)],
            [assigned(11), unassigned(12)],
            [unassigned(11), assigned(12)],
        ]
    )
    fallback = SimpleNamespace(notice=None)

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(
            approval_review.planning_service,
            "build_inside_run",
            AsyncMock(return_value=новый),
        ),
        patch.object(
            approval_review.plans_repository, "windows_plan_of", AsyncMock(return_value=None)
        ),
        patch.object(
            approval_review.plans_repository, "list_plan_assignments", assignments
        ),
        patch.object(
            approval_review,
            "preview_approval",
            AsyncMock(return_value=fallback),
        ) as preview,
    ):
        result = await approval_review.pick_windows(session, 40, office_id=1)

    assert result is fallback
    assert "№11" in fallback.notice
    assert "перенести или отменить" in fallback.notice
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    assert preview.await_args.args[1] == source.id


@pytest.mark.asyncio
async def test_window_search_needs_someone_to_call():
    find, approved, listed, counted = patched(draft(), [assigned(11)])

    with (
        find,
        approved,
        listed,
        counted,
        patch.object(
            approval_review.plans_repository, "windows_plan_of", AsyncMock(return_value=None)
        ),
        pytest.raises(PlanDataError, match="все заявки"),
    ):
        await approval_review.pick_windows(object(), 40, office_id=1)


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
        patch.object(approval_review.planning_service, "build_inside_run", AsyncMock()) as build,
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


def replan(plan_id=41, parent_id=40, voided_at=None):
    return SimpleNamespace(
        id=plan_id,
        plan_date=DAY,
        office_id=1,
        approved_at=None,
        parent_plan_id=parent_id,
        voided_at=voided_at,
        void_reason=None,
        solver="cuopt",
        objective_policy=None,
        input_snapshot={"request_order": [11, 12]},
    )


@pytest.mark.asyncio
async def test_replan_with_unfit_requests_is_reviewed_like_a_draft():
    """Круг у пересчёта тот же: по невлезшим решают отдельно, а не внутри самого пересчёта."""
    plan = replan()
    parent = SimpleNamespace(id=40, plan_date=DAY, office_id=1)
    repository = approval_review.plans_repository

    with (
        patch.object(approval_review.planning_service, "find_plan", AsyncMock(return_value=plan)),
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
    ):
        assert await approval_review.reviewable_plan(object(), 41, office_id=1) is plan


@pytest.mark.asyncio
async def test_replan_that_did_not_take_effect_is_not_reviewed():
    plan = replan(voided_at=at(12))
    plan.void_reason = "пока шли расчёт и обзвон, появились заявки №13"

    with (
        patch.object(approval_review.planning_service, "find_plan", AsyncMock(return_value=plan)),
        pytest.raises(PlanInUseError, match="№13"),
    ):
        await approval_review.reviewable_plan(object(), 41, office_id=1)


@pytest.mark.asyncio
async def test_replan_waits_for_decisions_on_requests_the_running_plan_still_holds():
    """Пересчёт заявку не взял, но она пока «В плане» у действующего: решение всё равно нужно.

    Иначе в окне подбора «звонить некому», а в свой момент пересчёт вернул бы её в «Новые».
    """
    from src.models import RequestStatusId
    from src.services.planner import planning_service

    plan = SimpleNamespace(id=41, parent_plan_id=40)
    held = SimpleNamespace(
        request_id=12,
        engineer_id=None,
        unassigned_reason="",
        request=SimpleNamespace(status_id=RequestStatusId.PLANNED, approved_plan_id=40),
    )
    # эта закреплена за чужим планом — по ней решать нечего
    alien = SimpleNamespace(
        request_id=13,
        engineer_id=None,
        unassigned_reason="",
        request=SimpleNamespace(status_id=RequestStatusId.PLANNED, approved_plan_id=39),
    )

    with patch.object(
        planning_service.plans_repository,
        "list_plan_assignments",
        AsyncMock(return_value=[assigned(11), held, alien]),
    ):
        waiting = await planning_service.waiting_unassigned(object(), plan)

    assert [a.request_id for a in waiting] == [12]


@pytest.mark.asyncio
async def test_window_search_is_not_repeated_for_the_same_plan():
    """Окно закрыли, не решив: открываем снова и видим те же предложения, а не новый расклад."""
    picked = SimpleNamespace(id=41)

    with (
        patch.object(
            approval_review.planning_service, "find_plan", AsyncMock(return_value=draft())
        ),
        patch.object(
            approval_review.plans_repository, "get_approved_plan", AsyncMock(return_value=None)
        ),
        patch.object(
            approval_review.plans_repository, "windows_plan_of", AsyncMock(return_value=picked)
        ),
        patch.object(
            approval_review, "preview_approval", AsyncMock(return_value="прежние предложения")
        ) as preview,
        patch.object(approval_review.planning_service, "build_inside_run", AsyncMock()) as build,
    ):
        result = await approval_review.pick_windows(object(), 40, office_id=1)

    assert result == "прежние предложения"
    build.assert_not_awaited()
    assert preview.await_args.args[1] == 41


@pytest.mark.asyncio
async def test_broken_promise_is_asked_about_again():
    """Прошлое «согласен» было про другое время: новый подбор сдвинул заявку — спрашиваем снова.

    Иначе бригада приедет в 16:36 к клиенту, которому обещали 14:24, и никто об этом не узнает.
    """
    moved = offered(12, at(16, 36))
    moved.request.promised_from = at(14, 24)
    moved.request.window_start, moved.request.window_end = at(14, 24), at(14, 54)
    plan = draft()
    plan.input_snapshot = {"request_order": [11, 12], "widened_requests": [12]}
    find, approved, listed, counted = patched(plan, [assigned(11), moved])

    with find, approved, listed, counted, patch.object(
        approval_review.clock, "now", return_value=at(9)
    ):
        preview = await approval_review.preview_approval(object(), 40, office_id=1)

    [problem] = preview.unassigned
    assert problem.request_id == 12
    assert problem.suggested_start == at(16, 36)
    assert "обещали 14:24" in problem.reason


@pytest.mark.asyncio
async def test_operator_can_refuse_the_picked_windows():
    """Времена не подошли: расчёт подбора убираем, прежний пересчёт снова в игре."""
    picked = SimpleNamespace(
        id=41,
        approved_at=None,
        decisions_count=None,
        decisions_from_plan_id=40,
        input_snapshot={"widened_requests": [12]},
    )
    source = SimpleNamespace(
        id=40, voided_at=at(12), void_reason="Отменён пересчётом №41: план пересчитали заново"
    )
    session = SimpleNamespace(commit=AsyncMock())

    with (
        patch.object(
            approval_review.planning_service, "find_plan", AsyncMock(return_value=picked)
        ),
        patch.object(
            approval_review.plans_repository, "retired_by", AsyncMock(return_value=[source])
        ),
        patch.object(approval_review.plans_repository, "delete_plan", AsyncMock()) as removed,
    ):
        await approval_review.drop_windows(session, 41, office_id=1)

    assert removed.await_args.args[1] is picked
    assert (source.voided_at, source.void_reason) == (None, None)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_picked_windows_with_decisions_are_not_dropped():
    """Решения уже применены — заявки изменились, молча откатывать нельзя."""
    picked = SimpleNamespace(
        id=41,
        approved_at=None,
        decisions_count=1,
        decisions_from_plan_id=40,
        input_snapshot={"widened_requests": [12]},
    )

    with (
        patch.object(
            approval_review.planning_service, "find_plan", AsyncMock(return_value=picked)
        ),
        patch.object(approval_review.plans_repository, "delete_plan", AsyncMock()) as removed,
        pytest.raises(PlanInUseError, match="решения уже приняты"),
    ):
        await approval_review.drop_windows(object(), 41, office_id=1)

    removed.assert_not_awaited()
