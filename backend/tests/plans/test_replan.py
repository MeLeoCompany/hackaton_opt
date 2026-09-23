"""Пересчёт утверждённого плана с текущего момента: откуда продолжает бригада и что остаётся за ней."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.models import RequestStatusId
from src.schemas.plans import SolverName
from src.services.planner import planning_service, replan_service
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER

MSK = timezone(timedelta(hours=3))
NEW, PLANNED, DONE, IN_PROGRESS, EN_ROUTE = (
    RequestStatusId.NEW,
    RequestStatusId.PLANNED,
    RequestStatusId.DONE,
    RequestStatusId.IN_PROGRESS,
    RequestStatusId.EN_ROUTE,
)
PARENT = SimpleNamespace(id=22, plan_date=date(2026, 8, 17))
ENGINEER = SimpleNamespace(
    id=1,
    name="Первая",
    shift_start=datetime(2026, 8, 17, 9, tzinfo=MSK),
    start_latitude=55.0,
    start_longitude=37.0,
)


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


def assignment(order, request_id, status, start, *, plan_id=22, latitude=55.7):
    request = SimpleNamespace(
        id=request_id,
        status_id=status,
        approved_plan_id=plan_id,
        duration_minutes=60,
        latitude=latitude,
        longitude=37.6,
        departure_allowed_at=None,
    )
    return SimpleNamespace(
        engineer=ENGINEER,
        engineer_id=1,
        visit_order=order,
        planned_arrival_time=start,
        request=request,
        request_id=request_id,
    )


def fact(arrived=None, finished=None):
    return SimpleNamespace(arrived_at=arrived, finished_at=finished)


async def positions(assignments, facts, moment, told=None):
    with patch.object(
        replan_service.brigade_repository, "list_facts", AsyncMock(return_value=facts)
    ):
        return await replan_service.brigade_positions(object(), PARENT, assignments, moment, told)


@pytest.mark.asyncio
async def test_brigade_at_work_continues_from_there_when_it_finishes():
    route = [
        assignment(1, 10, DONE, at(10)),
        assignment(2, 11, IN_PROGRESS, at(12), latitude=55.8),
        assignment(3, 12, PLANNED, at(14)),
    ]
    facts = {10: fact(finished=at(11)), 11: fact(arrived=at(12, 20))}

    fixed, starts = await positions(route, facts, at(12, 30))

    assert [item.request_id for item in fixed[1]] == [10, 11]  # закрытая и начатая остаются
    assert (starts[1].latitude, starts[1].available_from) == (55.8, at(13, 20))


@pytest.mark.asyncio
async def test_brigade_after_last_done_waits_from_the_moment_of_replan():
    route = [assignment(1, 10, DONE, at(10)), assignment(2, 11, PLANNED, at(14))]

    _, starts = await positions(route, {10: fact(finished=at(11))}, at(12))

    assert starts[1].available_from == at(12)  # закончила в 11:00, но пересчёт — на 12:00


@pytest.mark.asyncio
async def test_brigade_that_has_not_left_starts_from_the_morning_point():
    route = [assignment(1, 10, PLANNED, at(10)), assignment(2, 11, NEW, at(12), plan_id=None)]

    fixed, starts = await positions(route, {}, at(9, 30))

    assert fixed == {}
    assert (starts[1].latitude, starts[1].available_from) == (55.0, at(9, 30))


@pytest.mark.asyncio
async def test_brigade_stuck_on_a_request_is_free_when_the_operator_was_told():
    # бригада застряла: плановые 60 минут уже не годятся, считаем со слов бригады
    route = [assignment(1, 10, IN_PROGRESS, at(12)), assignment(2, 11, PLANNED, at(14))]
    facts = {10: fact(arrived=at(12))}

    _, planned = await positions(route, facts, at(12, 30))
    _, told = await positions(route, facts, at(12, 30), {1: at(15, 30)})

    assert planned[1].available_from == at(13)
    assert told[1].available_from == at(15, 30)


@pytest.mark.asyncio
async def test_free_at_is_ignored_for_brigade_that_is_not_on_site():
    # закончила заявку или уже выехала — свободна по своим отметкам, «освободится в» не про неё
    done_route = [assignment(1, 10, DONE, at(12)), assignment(2, 11, PLANNED, at(14))]
    facts = {10: fact(arrived=at(12), finished=at(12, 40))}

    _, told = await positions(done_route, facts, at(13), {1: at(15, 30)})

    assert told[1].available_from == at(13)


@pytest.mark.asyncio
async def test_replan_is_outdated_if_brigades_marked_something_after_it():
    parent = SimpleNamespace(id=22)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        input_snapshot={"request_order": [12]},
        replanned_at=at(12),
    )
    # заявку 12 решатель раскладывал и отдал первой бригаде, а выехала к ней вторая
    started = assignment(1, 12, IN_PROGRESS, at(14))
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service, "stuck_brigades", AsyncMock(return_value={})),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=[started])),
        patch.object(planning_service, "brigades_at_work", AsyncMock(return_value={12: 2})),
        # пересчёт свежий: проверяем именно отметки, а не срок годности
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        pytest.raises(planning_service.PlanInUseError, match="после него менялись заявки №12"),
    ):
        await planning_service.approve_replan(object(), plan)


@pytest.mark.asyncio
async def test_stale_replan_is_not_approved():
    """Точка старта пересчёта прошла: по такому плану бригады опаздывают, ещё не выехав."""
    parent = SimpleNamespace(id=22)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        input_snapshot={"request_order": [12]},
        replanned_at=at(12),
    )
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service, "stuck_brigades", AsyncMock(return_value={})),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=[])),
        patch.object(planning_service.clock, "now", return_value=at(16)),
        pytest.raises(planning_service.PlanInUseError, match="рассчитан на выезд с 12:00"),
    ):
        await planning_service.approve_replan(object(), plan)


def stored_request(request_id, status, plan_id=22):
    return SimpleNamespace(
        id=request_id,
        office_id=1,
        status_id=status,
        status=SimpleNamespace(name={IN_PROGRESS: "В работе"}.get(status, "")),
        approved_plan_id=plan_id,
        window_start=at(18),
        window_end=at(20),
        promised_from=None,
        promised_to=None,
        moved_from=None,
        cancel_reason=None,
        needs_followup=False,
    )


async def decide(decisions, requests):
    from src.schemas.plans import ReplanDecision

    history = []
    change_status = AsyncMock()
    with (
        patch.object(
            replan_service.requests_repository,
            "get_request",
            AsyncMock(side_effect=lambda session, request_id: requests[request_id]),
        ),
        patch.object(replan_service.request_status_service, "require_transition", AsyncMock()),
        patch.object(replan_service.request_status_service, "change_status", change_status),
        patch.object(
            replan_service.request_statuses_repository,
            "list_statuses",
            AsyncMock(return_value=[SimpleNamespace(id=NEW, name="Новая")]),
        ),
        patch.object(
            replan_service.request_statuses_repository,
            "add_history",
            lambda *args, **kwargs: history.append((args[1:], kwargs)),
        ),
    ):
        session = SimpleNamespace(flush=AsyncMock())
        await replan_service.apply_decisions(
            session,
            PARENT,
            [ReplanDecision(**decision) for decision in decisions],
            office_id=1,
            user_id=5,
        )
    return history, change_status


@pytest.mark.asyncio
async def test_move_to_another_day_takes_request_off_the_plan():
    request = stored_request(12, PLANNED)
    tomorrow = {
        "window_start": datetime(2026, 8, 18, 18, tzinfo=MSK),
        "window_end": datetime(2026, 8, 18, 20, tzinfo=MSK),
    }

    history, _ = await decide([{"request_id": 12, "action": "move", **tomorrow}], {12: request})

    assert (request.status_id, request.approved_plan_id) == (NEW, None)
    assert (request.window_start, request.window_end) == (
        tomorrow["window_start"],
        tomorrow["window_end"],
    )
    # перенос помним отметкой, узкое обещанное окно на новый день не тащим
    assert request.moved_from == PARENT.plan_date
    assert (request.promised_from, request.promised_to) == (None, None)
    assert history[0][0] == ([12], PLANNED, NEW)
    assert "Перенесена по договорённости" in history[0][1]["comment"]


@pytest.mark.asyncio
async def test_agreed_window_is_remembered_as_a_promise():
    request = stored_request(12, PLANNED)
    agreed = {
        "window_start": datetime(2026, 8, 17, 17, 40, tzinfo=MSK),
        "window_end": datetime(2026, 8, 17, 18, 10, tzinfo=MSK),
    }

    history, _ = await decide([{"request_id": 12, "action": "agree", **agreed}], {12: request})

    assert (request.promised_from, request.promised_to) == (
        agreed["window_start"],
        agreed["window_end"],
    )
    assert request.moved_from is None
    assert "Согласовано с клиентом" in history[0][1]["comment"]


@pytest.mark.asyncio
async def test_cancel_goes_through_status_transition():
    request = stored_request(12, PLANNED)

    _, change_status = await decide(
        [{"request_id": 12, "action": "cancel", "reason": "клиент отказался"}], {12: request}
    )

    assert change_status.call_args.args[2] == RequestStatusId.CANCELLED
    assert "клиент отказался" in change_status.call_args.kwargs["comment"]
    assert request.cancel_reason == "клиент отказался"
    assert request.needs_followup is False


@pytest.mark.asyncio
async def test_no_answer_is_cancel_with_followup_mark():
    request = stored_request(12, PLANNED)

    _, change_status = await decide([{"request_id": 12, "action": "no_answer"}], {12: request})

    assert change_status.call_args.args[2] == RequestStatusId.CANCELLED
    assert request.cancel_reason == "не дозвонились"
    assert request.needs_followup is True


@pytest.mark.asyncio
async def test_started_request_is_not_decided_about():
    with pytest.raises(planning_service.PlanDataError, match="уже «В работе»"):
        await decide(
            [{"request_id": 12, "action": "cancel"}], {12: stored_request(12, IN_PROGRESS)}
        )


@pytest.mark.asyncio
async def test_replan_without_free_requests_still_saves_the_decisions():
    """Оператор перенёс последнюю заявку: раскладывать нечего, но перенос не должен откатиться."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17))
    loaded = SimpleNamespace(instance=SimpleNamespace(n_requests=0, n_engineers=3, travel_min={}))
    plan = SimpleNamespace(id=30, parent_plan_id=None, replanned_at=None)
    session = SimpleNamespace(flush=AsyncMock())

    with (
        patch.object(
            replan_service.plans_repository, "list_plan_assignments", AsyncMock(return_value=[])
        ),
        patch.object(replan_service.planner_loader, "load_day", AsyncMock(return_value=loaded)),
        patch.object(replan_service.planning_service, "solve_with", AsyncMock(return_value=None)),
        patch.object(
            replan_service.planning_service, "save_solution", AsyncMock(return_value=plan)
        ) as save,
    ):
        result = await replan_service.build_replan(
            session, parent, SolverName.CUOPT, DEFAULT_OBJECTIVE_ORDER, at(15), office_id=1
        )

    assert result.plan is plan
    assert plan.parent_plan_id == 22
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_replan_starts_with_a_reserve_for_the_calculation():
    """Считаем не «прямо сейчас»: пока идёт расчёт и обзвон, время уходит."""
    parent = SimpleNamespace(
        id=22, plan_date=date(2026, 8, 17), approved_at=at(9), superseded_at=None, office_id=1
    )
    with (
        patch.object(replan_service.planning_service, "find_plan", AsyncMock(return_value=parent)),
        patch.object(replan_service.clock, "now", return_value=at(12)),
    ):
        _, start = await replan_service.replannable(object(), 22, None, office_id=1)

    assert start == at(12) + timedelta(minutes=settings.replan_lead_minutes)


@pytest.mark.asyncio
async def test_new_request_during_the_calculation_is_not_approved():
    """Пока считали и обзванивали, пришла заявка, которой пересчёт не видел."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        replanned_at=at(12),
        input_snapshot={"request_order": [12], "day_requests": [12, 13]},
    )
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service, "stuck_brigades", AsyncMock(return_value={})),
        patch.object(
            planning_service.day_state,
            "new_since",
            AsyncMock(return_value=["появились заявки №99"]),
        ),
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        pytest.raises(planning_service.PlanInUseError, match="появились заявки №99"),
    ):
        await planning_service.approve_replan(object(), plan)


@pytest.mark.asyncio
async def test_new_request_after_an_empty_day_snapshot_is_not_approved():
    """Пустой список — тоже снимок дня, а не отсутствие проверки актуальности."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        replanned_at=at(12),
        input_snapshot={"request_order": [], "day_requests": []},
    )
    repository = planning_service.plans_repository
    new_since = AsyncMock(return_value=["появились заявки №99"])
    session = object()
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service.day_state, "new_since", new_since),
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        pytest.raises(planning_service.PlanInUseError, match="появились заявки №99"),
    ):
        await planning_service.approve_replan(session, plan)

    new_since.assert_awaited_once_with(session, parent, [])


@pytest.mark.asyncio
async def test_brigade_that_left_as_the_replan_plans_does_not_block_approval():
    """Бригада выехала, пока шёл расчёт, — но туда же, куда её ведёт пересчёт: утверждаем."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        replanned_at=at(12),
        input_snapshot={"request_order": [12, 13], "day_requests": [12, 13]},
    )
    # первым визитом пересчёт даёт бригаде заявку 12 — на неё она и выехала
    route = [assignment(1, 12, EN_ROUTE, at(12, 30)), assignment(2, 13, PLANNED, at(14))]
    repository = planning_service.plans_repository
    session = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service, "stuck_brigades", AsyncMock(return_value={})),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=route)),
        patch.object(repository, "list_bound_requests", AsyncMock(return_value=[])),
        patch.object(planning_service, "brigades_at_work", AsyncMock(return_value={12: 1})),
        # заявка, на которую выехали, ушла из «Новых» и «В плане» — это не новая вводная
        patch.object(planning_service.day_state, "new_since", AsyncMock(return_value=[])),
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        patch.object(planning_service.request_status_service, "require_transition", AsyncMock()),
        patch.object(
            planning_service.request_statuses_repository,
            "list_statuses",
            AsyncMock(return_value=[SimpleNamespace(id=PLANNED, name="В плане")]),
        ),
        patch.object(planning_service.request_statuses_repository, "add_history"),
        patch.object(planning_service, "summarize_plans", AsyncMock(return_value=["итог"])),
    ):
        summary = await planning_service.approve_replan(session, plan)

    assert summary == "итог"
    # заявка осталась «В пути» и переехала на новый план вместе с бригадой
    assert route[0].request.status_id == EN_ROUTE
    assert route[0].request.approved_plan_id == plan.id


@pytest.mark.asyncio
async def test_brigade_that_jumped_the_queue_blocks_approval():
    """Бригада выехала не к ближайшей по пересчёту заявке — расхождение, считаем заново."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        replanned_at=at(12),
        input_snapshot={"request_order": [12, 13], "day_requests": [12, 13]},
    )
    # пересчёт ведёт бригаду сначала на 12, а выехала она на 13
    route = [assignment(1, 12, PLANNED, at(12, 30)), assignment(2, 13, EN_ROUTE, at(14))]
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(planning_service, "stuck_brigades", AsyncMock(return_value={})),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=route)),
        patch.object(planning_service, "brigades_at_work", AsyncMock(return_value={13: 1})),
        patch.object(planning_service.day_state, "new_since", AsyncMock(return_value=[])),
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        pytest.raises(planning_service.PlanInUseError, match="менялись заявки №13"),
    ):
        await planning_service.approve_replan(object(), plan)


@pytest.mark.asyncio
async def test_the_day_before_the_calculation_is_remembered_in_the_plan():
    """Список заявок дня снимается до расчёта и уезжает в план: по нему проверяет утверждение."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(id=31, input_snapshot={"request_order": [12]})
    session = SimpleNamespace(flush=AsyncMock())
    with (
        patch.object(
            replan_service.day_state, "of_plan", AsyncMock(return_value=[12, 13])
        ) as fingerprint,
        patch.object(
            replan_service.planning_service, "stuck_brigades", AsyncMock(return_value={1: "Первая"})
        ),
        patch.object(
            replan_service, "build_replan", AsyncMock(return_value=SimpleNamespace(plan=plan))
        ) as build,
        patch.object(
            replan_service.planning_service, "plan_routes", AsyncMock(return_value=([], False))
        ),
        patch.object(replan_service.planning_service, "set_plan_distance"),
    ):
        built = await replan_service.build_for_approval(
            session, parent, SolverName.CUOPT, DEFAULT_OBJECTIVE_ORDER, at(12), office_id=1
        )

    assert built is plan
    assert plan.input_snapshot["day_requests"] == [12, 13]
    assert plan.input_snapshot["stuck_brigades"] == [1]  # эта бригада стояла ещё до расчёта
    assert plan.input_snapshot["request_order"] == [12]
    # сначала смотрим день, потом считаем: отпечаток — про состояние до расчёта
    assert fingerprint.await_count == 1 and build.await_count == 1


@pytest.mark.asyncio
async def test_replan_lets_the_brigade_go_to_the_visit_it_plans_first():
    """Пока пересчёт ждёт утверждения, выезд открыт туда, куда ведёт и он."""
    route = [assignment(1, 12, DONE, at(11)), assignment(2, 13, PLANNED, at(13))]
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "unapproved_replan_id", AsyncMock(return_value=31)),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=route)),
    ):
        nearest = await planning_service.replan_next_visits(object(), 22)

    assert nearest == {1: 13}  # закрытые визиты пропущены: бригада едет к ближайшей открытой
    assert planning_service.sends_elsewhere(nearest, 1, 13) is False
    assert planning_service.sends_elsewhere(nearest, 1, 12) is True
    # пересчёта нет — шлагбаум по нему не опускается вовсе
    assert planning_service.sends_elsewhere(None, 1, 12) is False


@pytest.mark.asyncio
async def test_brigade_stuck_during_the_calculation_blocks_approval():
    """Пока считали и обзванивали, бригада выбилась из плана — пересчёт про неё уже неверен."""
    parent = SimpleNamespace(id=22, plan_date=date(2026, 8, 17), office_id=1)
    plan = SimpleNamespace(
        id=30,
        parent_plan_id=22,
        plan_date=date(2026, 8, 17),
        office_id=1,
        replanned_at=at(12),
        # на старте расчёта стояла только первая бригада — про неё пересчёт знал
        input_snapshot={"request_order": [12], "day_requests": [12], "stuck_brigades": [1]},
    )
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=[])),
        patch.object(planning_service.day_state, "new_since", AsyncMock(return_value=[])),
        patch.object(
            planning_service,
            "stuck_brigades",
            AsyncMock(return_value={1: "Первая", 2: "Вторая"}),
        ),
        patch.object(planning_service.clock, "now", return_value=at(12, 1)),
        pytest.raises(planning_service.PlanInUseError, match="выбились Вторая"),
    ):
        await planning_service.approve_replan(object(), plan)


@pytest.mark.asyncio
async def test_brigade_held_by_the_replan_is_not_counted_as_stuck():
    """Бригада стоит, потому что мы сами закрыли ей выезд на время пересчёта: это не «застряла»."""
    plan = SimpleNamespace(
        id=22, plan_date=date(2026, 8, 17), approved_at=at(9), superseded_at=None
    )
    route = [assignment(1, 12, PLANNED, at(10))]
    with (
        patch.object(
            planning_service.plans_repository,
            "list_plan_assignments",
            AsyncMock(return_value=route),
        ),
        patch.object(planning_service.brigade_repository, "list_facts", AsyncMock(return_value={})),
        patch.object(planning_service, "plan_route_delays", AsyncMock(return_value={})),
        # время выезда давно прошло: без пересчёта бригада считалась бы выбившейся
        patch.object(planning_service.clock, "now", return_value=at(14)),
    ):
        alone = await planning_service.stuck_brigades(object(), plan)
        held = await planning_service.stuck_brigades(object(), plan, {1: 99})

    assert list(alone) == [1]
    assert held == {}
