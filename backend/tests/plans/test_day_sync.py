"""Синхронизация дня с временем: что по плану к этому времени выполнено, что в работе."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.planner import day_sync_service

MSK = timezone(timedelta(hours=3))
DAY = date(2026, 8, 17)
NEW, PLANNED, DONE, CANCELLED, IN_PROGRESS = (
    RequestStatusId.NEW,
    RequestStatusId.PLANNED,
    RequestStatusId.DONE,
    RequestStatusId.CANCELLED,
    RequestStatusId.IN_PROGRESS,
)


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


ENGINEER = SimpleNamespace(name="Бригада Соколов", shift_start=at(9))


def visit(order, request_id, start, minutes=60, status=PLANNED, plan_id=22, office_id=1):
    request = SimpleNamespace(
        id=request_id,
        address=f"адрес {request_id}",
        duration_minutes=minutes,
        status_id=status,
        approved_plan_id=plan_id,
        office_id=office_id,
        work_type_id=1,  # дорога по нормативу 30 минут
    )
    return SimpleNamespace(
        engineer=ENGINEER,
        engineer_id=1,
        visit_order=order,
        planned_arrival_time=start,
        request=request,
    )


async def transitions(assignments, sync_time):
    with (
        patch.object(
            day_sync_service.plans_repository,
            "list_plan_assignments",
            AsyncMock(return_value=assignments),
        ),
        patch.object(
            day_sync_service.references_repository,
            "list_work_types",
            AsyncMock(return_value=[SimpleNamespace(id=1, travel_minutes=30)]),
        ),
    ):
        result = await day_sync_service.plan_transitions(object(), 22, sync_time, office_id=1)
    return [(item.request.id, item.to_status_id) for item in result]


@pytest.mark.asyncio
async def test_finished_work_is_done_and_brigade_on_the_way_to_the_next():
    route = [visit(1, 10, at(10)), visit(2, 11, at(12)), visit(3, 12, at(15))]

    # 12:30: первая закончилась в 11:00, по второй идут работы, к третьей ещё не выехали
    assert await transitions(route, at(12, 30)) == [(10, DONE), (11, IN_PROGRESS)]


@pytest.mark.asyncio
async def test_brigade_leaves_a_road_norm_before_the_work_starts():
    # работы в 20:00, дорога 30 минут — выезд в 19:30, а не с начала смены в 09:00
    assert await transitions([visit(1, 10, at(20))], at(19, 30)) == [(10, IN_PROGRESS)]
    assert await transitions([visit(1, 10, at(20))], at(19, 29)) == []


@pytest.mark.asyncio
async def test_brigade_cannot_leave_before_the_shift_or_the_previous_work_ends():
    # работы в 09:10, смена с 09:00: выезд в 09:00, не в 08:40
    assert await transitions([visit(1, 10, at(9, 10))], at(8, 59)) == []
    # вторая сразу после первой (до 11:00): выезд в 11:00, хотя по нормативу было бы 10:40
    route = [visit(1, 10, at(10)), visit(2, 11, at(11, 10))]
    assert await transitions(route, at(10, 50)) == [(10, IN_PROGRESS)]
    assert await transitions(route, at(11)) == [(10, DONE), (11, IN_PROGRESS)]


@pytest.mark.asyncio
async def test_closed_and_removed_visits_are_not_touched():
    route = [
        visit(1, 10, at(10), status=CANCELLED),
        visit(2, 11, at(12), status=DONE),
        visit(3, 12, at(13), status=NEW, plan_id=None),  # снята с плана
    ]

    assert await transitions(route, at(20)) == []


@pytest.mark.asyncio
async def test_new_request_outside_plan_with_expired_window_is_cancelled_with_warning():
    expired = SimpleNamespace(
        id=7, status_id=NEW, approved_plan_id=None, window_start=at(10), window_end=at(12)
    )
    still_open = SimpleNamespace(
        id=8, status_id=NEW, approved_plan_id=None, window_start=at(12), window_end=at(18)
    )
    in_plan = SimpleNamespace(
        id=9, status_id=PLANNED, approved_plan_id=22, window_start=at(9), window_end=at(11)
    )
    with patch.object(
        day_sync_service.requests_repository,
        "list_active_requests_in_period",
        AsyncMock(return_value=[expired, still_open, in_plan]),
    ):
        result = await day_sync_service.expired_new_requests(object(), DAY, at(13), office_id=1)

    assert [(item.request.id, item.to_status_id, item.warning) for item in result] == [
        (7, CANCELLED, True)
    ]


@pytest.mark.asyncio
async def test_sync_time_cannot_go_back():
    last = SimpleNamespace(synced_to=at(14, 30))
    with (
        patch.object(
            day_sync_service.plans_repository,
            "get_day_sync",
            AsyncMock(return_value=(last, "Иван")),
        ),
        pytest.raises(day_sync_service.DaySyncError, match="назад время не откатывается"),
    ):
        await day_sync_service.sync_day(object(), DAY, at(14), office_id=1, user_id=1, apply=False)
