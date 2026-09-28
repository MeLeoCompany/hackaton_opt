"""Черновик идущего дня живёт до своего момента выезда (docs/algoV2.md, шаги 1 и 6).

День считается на выезд «сейчас плюс запас»: эти минуты оператор смотрит маршруты, подбирает
окна и обзванивает клиентов. Позже утверждать нечего — маршруты начинались бы в прошлом; и
если за это время день изменился (пришла или отменилась заявка), тоже нечего: расчёт её не
видел. В обоих случаях день считают заново.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.services.planner import planning_service
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER
from src.services.planner.planning_service import PlanInUseError

MSK = timezone(timedelta(hours=3))
DAY = date(2026, 8, 17)
LEAD = timedelta(minutes=settings.replan_lead_minutes)


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


def draft(effective_at=None, day_requests=(11, 12)):
    return SimpleNamespace(
        id=40,
        plan_date=DAY,
        office_id=1,
        approved_at=None,
        effective_at=effective_at,
        input_snapshot={"request_order": [11, 12], "day_requests": list(day_requests)},
    )


def test_running_day_is_counted_for_departure_through_the_lead():
    with patch.object(planning_service.clock, "now", return_value=at(10)):
        assert planning_service.departure_moment(DAY) == at(10) + LEAD


def test_future_day_has_no_departure_moment():
    """День впереди — бригады выедут со своих смен, торопиться с утверждением некуда."""
    with patch.object(planning_service.clock, "now", return_value=at(10) - timedelta(days=3)):
        assert planning_service.departure_moment(DAY) is None


@pytest.mark.asyncio
async def test_draft_is_fresh_until_its_departure_moment():
    with (
        patch.object(planning_service.clock, "now", return_value=at(10, 10)),
        patch.object(planning_service.day_state, "new_since", AsyncMock(return_value=[])),
    ):
        reason = await planning_service.draft_stale_reason(object(), draft(at(10, 15)))

    assert reason is None


@pytest.mark.asyncio
async def test_draft_is_stale_after_its_departure_moment():
    with (
        patch.object(planning_service.clock, "now", return_value=at(10, 40)),
        patch.object(planning_service.day_state, "new_since", AsyncMock(return_value=[])),
    ):
        reason = await planning_service.draft_stale_reason(object(), draft(at(10, 15)))

    assert "10:15" in reason and "10:40" in reason


@pytest.mark.asyncio
async def test_draft_is_stale_when_the_day_changed_while_calling():
    with (
        patch.object(planning_service.clock, "now", return_value=at(10, 10)),
        patch.object(
            planning_service.day_state,
            "new_since",
            AsyncMock(return_value=["появились заявки №13"]),
        ) as news,
    ):
        reason = await planning_service.draft_stale_reason(object(), draft(at(10, 15)))

    assert news.await_args.args[2] == [11, 12]  # сверяется со снимком начала расчёта
    assert "появились заявки №13" in reason


@pytest.mark.asyncio
async def test_draft_of_a_future_day_never_goes_stale():
    """Момента выезда нет — считать нечего, день сверяется при утверждении обычным порядком."""
    with patch.object(planning_service.day_state, "new_since", AsyncMock()) as news:
        assert await planning_service.draft_stale_reason(object(), draft(None)) is None

    news.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_draft_is_not_approved():
    target = draft(at(10, 15))
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=target)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=None)),
        patch.object(
            planning_service,
            "draft_stale_reason",
            AsyncMock(return_value="Черновик №40 посчитан на выезд с 10:15"),
        ),
        patch.object(repository, "hold_plan_requests", AsyncMock()) as hold,
        pytest.raises(PlanInUseError, match="10:15"),
    ):
        await planning_service.approve_plan(SimpleNamespace(), 40, office_id=1)

    hold.assert_not_awaited()  # заявки за таким планом не закрепляем


@pytest.mark.asyncio
async def test_build_remembers_the_departure_moment_and_the_requests_of_the_day():
    plan = SimpleNamespace(
        id=7, total_distance_km=None, distance_provider=None, input_snapshot={"request_order": [11]}
    )
    with (
        patch.object(planning_service.clock, "now", return_value=at(10)),
        patch.object(
            planning_service,
            "load_planning_day",
            AsyncMock(return_value=SimpleNamespace(instance="")),
        ) as load,
        patch.object(planning_service.day_state, "request_ids", AsyncMock(return_value=[11, 12])),
        patch.object(planning_service, "solve_with", AsyncMock(return_value=SimpleNamespace())),
        patch.object(planning_service, "save_solution", AsyncMock(return_value=plan)),
        patch.object(planning_service, "plan_routes", AsyncMock(return_value=([], False))),
    ):
        built = await planning_service.build_inside_run(
            SimpleNamespace(),
            DAY,
            planning_service.SolverName.CUOPT,
            DEFAULT_OBJECTIVE_ORDER,
            office_id=1,
        )

    # бригады в задаче свободны не раньше момента выезда
    assert load.await_args.kwargs["not_before"] == at(10) + LEAD
    assert built.effective_at == at(10) + LEAD
    assert built.input_snapshot["day_requests"] == [11, 12]


def test_long_list_of_new_requests_is_shortened():
    """Причина уходит в подсказку и сообщение: перечень из полусотни номеров там не читают."""
    from src.services.planner import day_state

    assert day_state.listed([1, 2, 3]) == "№1, №2, №3"
    assert day_state.listed(list(range(1, 9))) == "№1, №2, №3, №4, №5 и ещё 3"
