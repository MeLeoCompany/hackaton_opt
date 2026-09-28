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


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=UTC)


def plan(plan_id, approved_at=None, plan_date=date(2026, 8, 17)):
    return SimpleNamespace(
        id=plan_id, plan_date=plan_date, approved_at=approved_at, office_id=OFFICE
    )


@pytest.fixture(autouse=True)
def transitions_allowed():
    # таблица переходов и история в этих тестах не проверяются: для них отдельные тесты статусов
    with (
        patch.object(
            planning_service.request_status_service, "require_transition", AsyncMock()
        ) as require,
        patch.object(planning_service.request_statuses_repository, "add_history"),
    ):
        yield require


@pytest.fixture(autouse=True)
def nothing_left_undecided():
    # по умолчанию все заявки черновика вошли в план — утверждать можно
    with patch.object(
        planning_service.plans_repository, "list_plan_assignments", AsyncMock(return_value=[])
    ) as listed:
        yield listed


@pytest.fixture(autouse=True)
def equipment_is_issued():
    # Проверка содержимого выдачи тестируется отдельно; здесь по умолчанию комплект полный.
    with patch.object(
        planning_service.equipment_issue,
        "plan_stock_problems",
        AsyncMock(return_value=[]),
    ) as checked:
        yield checked


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
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(3, 3, []))) as hold,
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=[summary(9)])),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    assert hold.await_args.args[1] is target
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approval_requires_equipment_to_be_issued(equipment_is_issued):
    target = plan(9)
    session = SimpleNamespace(commit=AsyncMock())
    equipment_is_issued.return_value = ["Бригада Арташкин: «Роутер» нужно 4, выдано 2"]

    with (
        patch.object(planning_service.plans_repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(
            planning_service.plans_repository, "get_approved_plan", AsyncMock(return_value=None)
        ),
        pytest.raises(PlanInUseError, match="оборудование ещё не выдано"),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_draft_with_undecided_requests_is_not_approved(nothing_left_undecided):
    """Невлезшую заявку не оставляют «Новой» без решения: перенос, согласование или отмена."""
    from src.models import RequestStatusId

    def unassigned(request_id, status, approved_plan_id=None):
        request = SimpleNamespace(status_id=status, approved_plan_id=approved_plan_id)
        return SimpleNamespace(request_id=request_id, engineer_id=None, request=request)

    nothing_left_undecided.return_value = [
        unassigned(12, RequestStatusId.NEW),
        # за другим планом или уже отменена — решать по ней нечего
        unassigned(13, RequestStatusId.PLANNED, approved_plan_id=5),
        unassigned(14, RequestStatusId.CANCELLED),
    ]
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan(9))),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock()) as hold,
        pytest.raises(PlanInUseError, match="№12:") as error,
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    assert "№13" not in str(error.value) and "№14" not in str(error.value)
    hold.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_plan_cannot_steal_requests_held_by_another_plan():
    target = plan(9)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(2, 3, []))),
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
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(3, 3, []))),
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
    # план будущего дня, по которому ни одна бригада не отмечалась: снять утверждение можно
    target = plan(9, datetime.now(UTC), plan_date=date(2099, 1, 1))
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "has_brigade_marks", AsyncMock(return_value=False)),
        patch.object(repository, "release_plan_requests", AsyncMock(return_value=[])) as release,
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=[summary(9)])),
    ):
        await planning_service.cancel_plan_approval(session, 9, office_id=OFFICE)

    release.assert_awaited_once_with(session, target)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approval_of_a_plan_in_work_is_not_cancelled():
    """День плана настал — бригады видят его в приложении; менять план можно только пересчётом."""
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=plan(9, datetime.now(UTC)))),
        patch.object(repository, "release_plan_requests", AsyncMock()) as release,
        pytest.raises(PlanInUseError, match="уже работают"),
    ):
        await planning_service.cancel_plan_approval(session, 9, office_id=OFFICE)

    release.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_with_brigade_marks_is_in_work_before_its_day():
    """Бригада уже отметилась по заявке плана — он в работе, даже если день ещё не наступил."""
    target = plan(9, datetime.now(UTC), plan_date=date(2099, 1, 1))
    repository = planning_service.plans_repository

    with patch.object(repository, "has_brigade_marks", AsyncMock(return_value=True)) as marks:
        assert await planning_service.plan_in_work(AsyncMock(), target) is True

    marks.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_plan_with_unanswered_offer_is_not_approved(nothing_left_undecided):
    """Подобранное окно — предложение клиенту: пока ответа нет, утверждать нельзя.

    Иначе бригада приедет в то время, о котором с клиентом никто не договаривался.
    """
    target = plan(9)
    target.input_snapshot = {"widened_requests": [12]}
    # расчёт поставил заявку далеко за её окно: это предложение, а не согласие
    offered = SimpleNamespace(
        request_id=12,
        engineer_id=1,
        planned_arrival_time=at(17),
        request=SimpleNamespace(promised_from=None, window_start=at(10), window_end=at(11)),
    )
    nothing_left_undecided.return_value = [offered]
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock()) as hold,
        pytest.raises(PlanInUseError, match="№12"),
    ):
        await planning_service.approve_plan(object(), 9, office_id=OFFICE)

    hold.assert_not_awaited()


@pytest.mark.asyncio
async def test_agreed_offer_no_longer_blocks_approval(nothing_left_undecided):
    """Клиент согласился — отметка «согласовано» стоит, и план утверждается как есть."""
    target = plan(9)
    target.input_snapshot = {"widened_requests": [12]}
    # окно сужено до обещанного, и расчёт ставит заявку ровно в него
    agreed = SimpleNamespace(
        request_id=12,
        engineer_id=1,
        planned_arrival_time=at(14),
        request=SimpleNamespace(promised_from=at(14), window_start=at(14), window_end=at(14, 30)),
    )
    nothing_left_undecided.return_value = [agreed]
    session = SimpleNamespace(commit=AsyncMock())
    repository = planning_service.plans_repository

    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(repository, "hold_plan_requests", AsyncMock(return_value=(3, 3, []))) as hold,
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=[summary(9)])),
    ):
        await planning_service.approve_plan(session, 9, office_id=OFFICE)

    hold.assert_awaited_once()
