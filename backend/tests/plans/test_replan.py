"""Пересчёт утверждённого плана с текущего момента: откуда продолжает бригада и что остаётся за ней."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.planner import planning_service, replan_service

MSK = timezone(timedelta(hours=3))
NEW, PLANNED, DONE, IN_PROGRESS = (
    RequestStatusId.NEW,
    RequestStatusId.PLANNED,
    RequestStatusId.DONE,
    RequestStatusId.IN_PROGRESS,
)
PARENT = SimpleNamespace(id=22)
ENGINEER = SimpleNamespace(
    id=1,
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


async def positions(assignments, facts, moment):
    with patch.object(
        replan_service.brigade_repository, "list_facts", AsyncMock(return_value=facts)
    ):
        return await replan_service.brigade_positions(object(), PARENT, assignments, moment)


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
    # заявку 12 решатель раскладывал, а бригада после пересчёта уже выехала к ней
    started = assignment(1, 12, IN_PROGRESS, at(14))
    repository = planning_service.plans_repository
    with (
        patch.object(repository, "get_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "get_approved_plan", AsyncMock(return_value=parent)),
        patch.object(repository, "list_plan_assignments", AsyncMock(return_value=[started])),
        pytest.raises(planning_service.PlanInUseError, match="после него менялись заявки №12"),
    ):
        await planning_service.approve_replan(object(), plan)
