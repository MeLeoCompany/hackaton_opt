"""Отметки бригады в мобильном приложении: статус заявки и время факта."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.brigade import brigade_service

PLANNED, EN_ROUTE, IN_PROGRESS, DONE, CANCELLED = (
    RequestStatusId.PLANNED,
    RequestStatusId.EN_ROUTE,
    RequestStatusId.IN_PROGRESS,
    RequestStatusId.DONE,
    RequestStatusId.CANCELLED,
)
USER = SimpleNamespace(id=9, office_id=1, brigade_id=9, name="Бригада Соколов")


def request(status_id=PLANNED, plan_id=22):
    return SimpleNamespace(
        id=5,
        office_id=1,
        status_id=status_id,
        status=SimpleNamespace(name={DONE: "Выполнена", CANCELLED: "Отменена"}.get(status_id)),
        approved_plan_id=plan_id,
        departure_allowed_at=None,
        cancel_reason=None,
    )


async def mark(stored, action, reason="", *, in_route=True, fact=None):
    fact = fact or SimpleNamespace(
        departed_at=None, arrived_at=None, finished_at=None, updated_at=None
    )
    change_status = AsyncMock()
    assignment = SimpleNamespace(
        request_id=5, engineer_id=1, plan_id=22, request=stored, planned_arrival_time=None
    )
    with (
        patch.object(
            brigade_service.requests_repository, "get_request", AsyncMock(return_value=stored)
        ),
        patch.object(
            brigade_service,
            "route_assignments",
            AsyncMock(return_value=[assignment] if in_route else []),
        ),
        patch.object(
            brigade_service.brigade_repository, "get_or_add_fact", AsyncMock(return_value=fact)
        ),
        patch.object(brigade_service.request_status_service, "change_status", change_status),
        patch.object(
            brigade_service.plans_repository,
            "get_plan",
            AsyncMock(return_value=SimpleNamespace(id=22, plan_date="2026-08-17")),
        ),
        # выезд разрешён: бригада идёт по графику, пересчёта нет
        patch.object(
            brigade_service.planning_service, "plan_route_delays", AsyncMock(return_value={})
        ),
        patch.object(
            brigade_service.plans_repository, "has_unapproved_replan", AsyncMock(return_value=False)
        ),
        patch.object(brigade_service, "get_route", AsyncMock(return_value="маршрут")),
    ):
        session = SimpleNamespace(commit=AsyncMock())
        result = await brigade_service.mark(session, USER, 5, action, reason)
    targets = [(call.args[2], call.kwargs["comment"]) for call in change_status.call_args_list]
    return result, fact, targets


@pytest.mark.asyncio
async def test_departure_puts_request_en_route_and_remembers_the_time():
    result, fact, targets = await mark(request(), "depart")

    assert result == "маршрут"
    assert targets == [(EN_ROUTE, "Бригада выехала")]  # «В пути» — едет, ещё не на месте
    assert fact.departed_at is not None and fact.arrived_at is None


@pytest.mark.asyncio
async def test_arrival_puts_request_in_work_and_marks_departure_if_it_was_missed():
    _, fact, targets = await mark(request(), "arrive")

    assert targets == [(IN_PROGRESS, "Бригада на месте")]  # «В работе» — работает на месте
    assert fact.departed_at is not None and fact.arrived_at == fact.departed_at


@pytest.mark.asyncio
async def test_done_and_failure():
    _, fact, targets = await mark(request(IN_PROGRESS), "done")
    assert targets == [(DONE, "Бригада: выполнено")] and fact.finished_at is not None

    _, _, targets = await mark(request(IN_PROGRESS), "fail", "клиента нет дома")
    assert targets == [(CANCELLED, "Бригада: не выполнено — клиента нет дома")]


@pytest.mark.asyncio
async def test_closed_request_cannot_be_marked():
    with pytest.raises(brigade_service.BrigadeActionError, match="уже «Выполнена»"):
        await mark(request(DONE), "done")


@pytest.mark.asyncio
async def test_request_of_another_route_or_removed_from_plan_cannot_be_marked():
    with pytest.raises(brigade_service.BrigadeActionError, match="нет в маршруте бригады"):
        await mark(request(), "depart", in_route=False)
    with pytest.raises(brigade_service.BrigadeActionError, match="сняли с плана"):
        await mark(request(plan_id=None), "depart")


@pytest.mark.asyncio
async def test_departure_is_marked_once():
    fact = SimpleNamespace(departed_at="09:00", arrived_at=None, finished_at=None, updated_at=None)
    with pytest.raises(brigade_service.BrigadeActionError, match="уже отмечен"):
        await mark(request(EN_ROUTE), "depart", fact=fact)
