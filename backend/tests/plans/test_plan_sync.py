"""Синхронизация маршрутов с планом (режим демонстрации): бригада «идёт строго по плану»."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.planner import plan_sync

MSK = timezone(timedelta(hours=3))
PLANNED, EN_ROUTE, IN_PROGRESS, DONE, CANCELLED = (
    RequestStatusId.PLANNED,
    RequestStatusId.EN_ROUTE,
    RequestStatusId.IN_PROGRESS,
    RequestStatusId.DONE,
    RequestStatusId.CANCELLED,
)
PLAN = SimpleNamespace(id=22)


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


def test_state_follows_the_plan_at_any_moment():
    departed, start = at(9), at(10)  # выехала в 9, работа 10:00–11:00

    assert plan_sync.planned_state(departed, start, 60, at(8)).status_id == PLANNED
    assert plan_sync.planned_state(departed, start, 60, at(9, 30)).status_id == EN_ROUTE
    working = plan_sync.planned_state(departed, start, 60, at(10, 30))
    assert (working.status_id, working.arrived_at, working.finished_at) == (
        IN_PROGRESS,
        start,
        None,
    )
    done = plan_sync.planned_state(departed, start, 60, at(12))
    assert (done.status_id, done.finished_at) == (DONE, at(11))


def engineer(engineer_id):
    return SimpleNamespace(id=engineer_id, shift_start=at(9))


def assignment(engineer_id, order, request_id, start, status, plan_id=22):
    request = SimpleNamespace(
        id=request_id,
        status_id=status,
        approved_plan_id=plan_id,
        duration_minutes=60,
        departure_allowed_at=at(9),
    )
    return SimpleNamespace(
        engineer_id=engineer_id,
        engineer=engineer(engineer_id),
        visit_order=order,
        planned_arrival_time=start,
        request=request,
    )


async def synced(assignments, engineer_ids, now, travel_minutes=None):
    facts = {}

    async def fact(session, request_id, engineer_id):
        return facts.setdefault(request_id, SimpleNamespace(request_id=request_id))

    statuses = {status: SimpleNamespace(id=status) for status in RequestStatusId}
    with (
        patch.object(plan_sync.clock, "now", return_value=now),
        patch.object(
            plan_sync.plans_repository, "list_plan_assignments", AsyncMock(return_value=assignments)
        ),
        patch.object(
            plan_sync.request_statuses_repository,
            "list_statuses",
            AsyncMock(return_value=list(statuses.values())),
        ),
        patch.object(plan_sync.request_statuses_repository, "add_history") as history,
        patch.object(plan_sync.brigade_repository, "get_or_add_fact", side_effect=fact),
    ):
        counts = await plan_sync.sync_routes(
            SimpleNamespace(flush=AsyncMock()),
            PLAN,
            engineer_ids,
            user_id=7,
            travel_minutes=travel_minutes,
        )
    return counts, facts, history


@pytest.mark.asyncio
async def test_selected_route_is_brought_to_the_plan_and_others_stay():
    route = [
        assignment(1, 1, 10, at(10), PLANNED),
        assignment(1, 2, 11, at(12), PLANNED),
        assignment(1, 3, 12, at(14), PLANNED),
    ]
    other = [assignment(2, 1, 20, at(10), PLANNED)]

    counts, facts, _ = await synced(route + other, [1], at(12, 30))

    assert [a.request.status_id for a in route] == [DONE, IN_PROGRESS, PLANNED]
    # выехала сразу, как закончила предыдущую: в 11:00
    assert facts[11].departed_at == at(11)
    assert facts[11].arrived_at == at(12)
    assert other[0].request.status_id == PLANNED and 20 not in facts  # не выбран — не трогаем
    assert route[0].request.departure_allowed_at is None
    assert counts == {DONE: 1, IN_PROGRESS: 1, PLANNED: 1}


@pytest.mark.asyncio
async def test_moving_time_back_returns_done_work_to_the_plan():
    """Время отмотали назад — выполненное по плану снова «В плане», мимо таблицы переходов."""
    route = [assignment(1, 1, 10, at(10), DONE), assignment(1, 2, 11, at(12), DONE)]

    _, facts, history = await synced(route, [1], at(8))

    assert [a.request.status_id for a in route] == [PLANNED, PLANNED]
    assert facts[10].finished_at is None and facts[10].departed_at is None
    comments = {call.kwargs["comment"] for call in history.call_args_list}
    assert comments == {plan_sync.SYNC_COMMENT}  # правка видна в истории заявки


@pytest.mark.asyncio
async def test_cancelled_and_withdrawn_requests_are_left_alone():
    route = [
        assignment(1, 1, 10, at(10), CANCELLED),
        assignment(1, 2, 11, at(12), PLANNED, plan_id=None),  # сняли с плана
        assignment(1, 3, 12, at(14), PLANNED),
    ]

    _, facts, _ = await synced(route, [1], at(20))

    assert route[0].request.status_id == CANCELLED
    assert route[1].request.status_id == PLANNED
    assert set(facts) == {12}
    # следующая бригада выезжает после конца пропущенной работы, а не с утра
    assert facts[12].departed_at == at(13)


@pytest.mark.asyncio
async def test_brigade_leaves_so_that_it_arrives_on_time():
    """Выезд — начало работ минус время в пути, а не сразу после предыдущей заявки."""
    route = [assignment(1, 1, 10, at(10), PLANNED), assignment(1, 2, 11, at(14), PLANNED)]

    _, facts, _ = await synced(route, [1], at(13, 45), travel_minutes={10: 30, 11: 25})

    assert facts[10].departed_at == at(9, 30)
    assert facts[11].departed_at == at(13, 35)  # закончила в 11, выехала в 13:35
    assert route[1].request.status_id == EN_ROUTE


def test_travel_is_taken_from_plan_legs():
    road = SimpleNamespace(
        visits=[SimpleNamespace(request_id=10), SimpleNamespace(request_id=11)],
        legs=[
            SimpleNamespace(visit_index=None, duration_min=30, wait_min=0),
            SimpleNamespace(visit_index=None, duration_min=20, wait_min=0),
        ],
    )
    transit = SimpleNamespace(
        visits=[SimpleNamespace(request_id=20)],
        legs=[
            SimpleNamespace(visit_index=0, duration_min=5, wait_min=0),  # пешком до остановки
            SimpleNamespace(visit_index=0, duration_min=25, wait_min=7),  # автобус и ожидание
        ],
    )

    assert plan_sync.travel_by_request(SimpleNamespace(routes=[road, transit])) == {
        10: 30,
        11: 20,
        20: 37,
    }
