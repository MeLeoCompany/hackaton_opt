"""Статусы заявок: переходы только по таблице, ручные — оператором, системные — системой."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import RequestStatusId
from src.services.requests import request_status_service

NEW, PLANNED, DONE, CANCELLED, IN_PROGRESS = (
    RequestStatusId.NEW,
    RequestStatusId.PLANNED,
    RequestStatusId.DONE,
    RequestStatusId.CANCELLED,
    RequestStatusId.IN_PROGRESS,
)
STATUSES = [
    SimpleNamespace(id=NEW, name="Новая", plannable=True),
    SimpleNamespace(id=PLANNED, name="В плане", plannable=True),
    SimpleNamespace(id=DONE, name="Выполнена", plannable=False),
    SimpleNamespace(id=CANCELLED, name="Отменена", plannable=False),
    SimpleNamespace(id=IN_PROGRESS, name="В работе", plannable=False),
]
# та же таблица, что в db/init/022_request_status.sql
TRANSITIONS = [
    SimpleNamespace(
        from_status_id=NEW, to_status_id=PLANNED, manual=False, description="План утверждён"
    ),
    SimpleNamespace(
        from_status_id=PLANNED, to_status_id=NEW, manual=False, description="Утверждение снято"
    ),
    SimpleNamespace(
        from_status_id=PLANNED, to_status_id=DONE, manual=True, description="Выполнена"
    ),
    SimpleNamespace(from_status_id=NEW, to_status_id=CANCELLED, manual=True, description="Отмена"),
    SimpleNamespace(
        from_status_id=PLANNED, to_status_id=CANCELLED, manual=True, description="Отмена"
    ),
    SimpleNamespace(from_status_id=CANCELLED, to_status_id=NEW, manual=True, description="Возврат"),
    SimpleNamespace(
        from_status_id=PLANNED, to_status_id=IN_PROGRESS, manual=True, description="Выехала"
    ),
    SimpleNamespace(
        from_status_id=IN_PROGRESS, to_status_id=DONE, manual=True, description="Готово"
    ),
    SimpleNamespace(
        from_status_id=IN_PROGRESS, to_status_id=CANCELLED, manual=True, description="Отмена"
    ),
]
# маршрут бригады утверждённого плана, по которому проверяются разрывы; по умолчанию пусто
ROUTES: list = []


@pytest.fixture(autouse=True)
def status_tables():
    repository = request_status_service.request_statuses_repository
    ROUTES.clear()
    with (
        patch.object(repository, "list_statuses", AsyncMock(return_value=STATUSES)),
        patch.object(repository, "list_transitions", AsyncMock(return_value=TRANSITIONS)),
        patch.object(
            repository, "list_routes_of", AsyncMock(side_effect=lambda session, requests: ROUTES)
        ),
        patch.object(repository, "add_history") as add_history,
    ):
        yield add_history


def request(request_id, status_id, plan_id=None):
    return SimpleNamespace(
        id=request_id, status_id=status_id, status=None, approved_plan_id=plan_id
    )


@pytest.mark.asyncio
async def test_operator_marks_planned_request_done():
    planned = request(7, PLANNED)

    await request_status_service.change_status(object(), [planned], DONE, manual=True)

    assert planned.status_id == DONE
    assert planned.status.name == "Выполнена"


@pytest.mark.asyncio
async def test_transition_missing_from_table_is_forbidden():
    done = request(7, DONE)

    with pytest.raises(
        request_status_service.StatusTransitionError, match="из «Выполнена» в «Новая»"
    ):
        await request_status_service.change_status(object(), [done], NEW, manual=True)


@pytest.mark.asyncio
async def test_operator_cannot_do_system_transition():
    new = request(7, NEW)

    # в «В плане» заявка переходит сама при утверждении плана
    with pytest.raises(request_status_service.StatusTransitionError, match="переходит сама"):
        await request_status_service.change_status(object(), [new], PLANNED, manual=True)


@pytest.mark.asyncio
async def test_system_cannot_do_manual_transition():
    planned = request(7, PLANNED)

    with pytest.raises(request_status_service.StatusTransitionError, match="только оператор"):
        await request_status_service.change_status(object(), [planned], DONE, manual=False)


@pytest.mark.asyncio
async def test_one_forbidden_transition_changes_nothing():
    new, done = request(1, NEW), request(2, DONE)

    with pytest.raises(request_status_service.StatusTransitionError):
        await request_status_service.change_status(object(), [new, done], CANCELLED, manual=True)

    assert new.status_id == NEW


@pytest.mark.asyncio
async def test_same_status_is_not_a_transition():
    cancelled = request(1, CANCELLED)

    await request_status_service.change_status(object(), [cancelled], CANCELLED, manual=True)

    assert cancelled.status_id == CANCELLED


@pytest.mark.asyncio
async def test_approval_transition_must_be_in_table():
    await request_status_service.require_transition(object(), NEW, PLANNED, manual=False)

    with pytest.raises(request_status_service.StatusTransitionError):
        await request_status_service.require_transition(object(), NEW, DONE, manual=False)


@pytest.mark.asyncio
async def test_status_change_is_written_to_history(status_tables):
    planned = request(7, PLANNED)

    await request_status_service.change_status(
        object(), [planned], DONE, manual=True, user_id=3, comment="отметил"
    )

    status_tables.assert_called_once()
    args, kwargs = status_tables.call_args
    assert args[1:] == ([7], PLANNED, DONE)
    assert kwargs == {"manual": True, "user_id": 3, "plan_id": None, "comment": "отметил"}


def route(*statuses):
    """Маршрут бригады утверждённого плана №22: заявки 1, 2, 3... по порядку визитов."""
    visits = [
        request(number, status, plan_id=22) for number, status in enumerate(statuses, start=1)
    ]
    ROUTES.append(visits)
    return visits


@pytest.mark.asyncio
async def test_next_visit_cannot_start_before_previous_is_done():
    _, second, _ = route(PLANNED, PLANNED, PLANNED)

    with pytest.raises(
        request_status_service.StatusTransitionError, match="сначала закройте заявку №1"
    ):
        await request_status_service.change_status(object(), [second], IN_PROGRESS, manual=True)

    assert second.status_id == PLANNED


@pytest.mark.asyncio
async def test_visit_cannot_be_done_while_earlier_one_is_in_progress():
    _, second = route(IN_PROGRESS, PLANNED)

    with pytest.raises(request_status_service.StatusTransitionError, match="визит 1"):
        await request_status_service.change_status(object(), [second], DONE, manual=True)


@pytest.mark.asyncio
async def test_first_visit_starts_freely_and_next_after_it_is_done():
    _, second, _ = route(DONE, PLANNED, PLANNED)

    await request_status_service.change_status(object(), [second], IN_PROGRESS, manual=True)

    assert second.status_id == IN_PROGRESS


@pytest.mark.asyncio
async def test_cancelled_visit_is_not_a_gap():
    *_, third = route(CANCELLED, DONE, PLANNED)

    await request_status_service.change_status(object(), [third], IN_PROGRESS, manual=True)

    assert third.status_id == IN_PROGRESS


@pytest.mark.asyncio
async def test_several_visits_of_the_route_can_be_closed_together():
    first, second, _ = route(IN_PROGRESS, PLANNED, PLANNED)

    # первая и вторая отмечены выполненными одним действием — итоговое состояние без разрыва
    await request_status_service.change_status(object(), [first, second], DONE, manual=True)

    assert (first.status_id, second.status_id) == (DONE, DONE)


@pytest.mark.asyncio
async def test_request_returned_to_new_leaves_the_plan():
    cancelled = request(9, CANCELLED, plan_id=22)

    await request_status_service.change_status(object(), [cancelled], NEW, manual=True)

    assert (cancelled.status_id, cancelled.approved_plan_id) == (NEW, None)
