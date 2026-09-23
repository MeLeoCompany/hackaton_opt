"""Групповая правка и удаление заявок: галочки в таблице, одно действие на все отмеченные.

Правка идёт целиком или никак: если хоть одну заявку менять нельзя, данные не трогаются.
Удаление наоборот — удаляем всё, что можно, а про остальные возвращаем причины.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.local_day import local_timezone
from src.models import RequestStatusId
from src.schemas.requests import RequestBulkUpdate
from src.services.requests import requests_service

NEW, PLANNED = RequestStatusId.NEW, RequestStatusId.PLANNED
NAMES = {NEW: "Новая", PLANNED: "В плане"}


def stored(request_id, status_id=NEW, hour=10):
    return SimpleNamespace(
        id=request_id,
        office_id=1,
        status_id=status_id,
        status=SimpleNamespace(name=NAMES[status_id]),
        address=f"Ленина, {request_id}",
        latitude=Decimal("55.7"),
        longitude=Decimal("37.6"),
        duration_minutes=60,
        window_start=datetime(2026, 8, 17, hour, tzinfo=local_timezone()),
        window_end=datetime(2026, 8, 17, hour + 3, tzinfo=local_timezone()),
        priority_id=3,
        skill_id=2,
        transport_id=None,
        work_type_id=1,
        equipment=[],
    )


def references(work_minutes=45):
    options = SimpleNamespace(id_by_key={"1": 1, "2": 2, "3": 3})
    return SimpleNamespace(
        priorities=options,
        skills=options,
        work_types=options,
        transports=options,
        equipment=options,
        work_type_norms={1: SimpleNamespace(skill_id=3, work_minutes=work_minutes)},
    )


async def bulk_update(requests, payload, change_status=None):
    session = SimpleNamespace(commit=AsyncMock())
    with (
        patch.object(
            requests_service.request_status_service,
            "change_status",
            change_status or AsyncMock(),
        ),
        patch.object(
            requests_service.requests_repository,
            "get_requests_by_ids",
            AsyncMock(return_value={request.id: request for request in requests}),
        ),
        patch.object(
            requests_service, "load_reference_lookup", AsyncMock(return_value=references())
        ),
    ):
        return await requests_service.update_requests(session, payload, office_id=1)


@pytest.mark.asyncio
async def test_only_marked_fields_change():
    """Отметили приоритет — остальное у каждой заявки осталось своим."""
    requests = [stored(1), stored(2, hour=14)]

    report = await bulk_update(requests, RequestBulkUpdate(request_ids=[1, 2], priority_id=1))

    assert report.updated == 2
    assert [request.priority_id for request in requests] == [1, 1]
    assert requests[0].window_start.hour == 10 and requests[1].window_start.hour == 14
    assert [request.duration_minutes for request in requests] == [60, 60]


@pytest.mark.asyncio
async def test_day_transfer_keeps_the_time_of_day():
    requests = [stored(1, hour=9), stored(2, hour=16)]

    await bulk_update(
        requests, RequestBulkUpdate(request_ids=[1, 2], move_to_day=date(2026, 8, 20))
    )

    starts = [request.window_start.astimezone(local_timezone()) for request in requests]
    ends = [request.window_end.astimezone(local_timezone()) for request in requests]
    assert [moment.date() for moment in starts] == [date(2026, 8, 20)] * 2
    assert [moment.hour for moment in starts] == [9, 16]
    assert [moment.hour for moment in ends] == [12, 19]


@pytest.mark.asyncio
async def test_work_type_brings_its_skill_and_norm():
    requests = [stored(1)]

    await bulk_update(requests, RequestBulkUpdate(request_ids=[1], work_type_id=1))

    assert requests[0].skill_id == 3
    assert requests[0].duration_minutes == 45  # норматив типа работ


@pytest.mark.asyncio
async def test_request_in_plan_stops_the_whole_group():
    requests = [stored(1), stored(2, status_id=PLANNED)]

    with pytest.raises(requests_service.RequestDataError, match="№2 уже «В плане»"):
        await bulk_update(requests, RequestBulkUpdate(request_ids=[1, 2], priority_id=1))

    assert [request.priority_id for request in requests] == [3, 3]  # не изменилось ничего


@pytest.mark.asyncio
async def test_window_that_turns_upside_down_is_refused():
    requests = [stored(1, hour=9)]
    payload = RequestBulkUpdate(request_ids=[1], window_start=datetime(2026, 8, 17, 18, tzinfo=UTC))

    with pytest.raises(requests_service.RequestDataError, match="конец окна должен быть позже"):
        await bulk_update(requests, payload)


@pytest.mark.asyncio
async def test_delete_removes_what_it_can_and_explains_the_rest():
    async def delete_one(session, request_id, office_id):
        if request_id == 2:
            raise requests_service.RequestInUseError(
                f"Заявку №{request_id} нельзя удалить: она в плане"
            )

    with patch.object(requests_service, "delete_request", AsyncMock(side_effect=delete_one)):
        report = await requests_service.delete_requests(object(), [1, 2, 3, 3], office_id=1)

    assert report.deleted == 2  # повтор номера не считается дважды
    assert [problem.id for problem in report.problems] == [2]
    assert "нельзя удалить" in report.problems[0].reason


@pytest.mark.asyncio
async def test_status_changes_even_for_a_request_in_plan():
    """Статус — не поле заявки, а переход: его меняют и у той, которую править нельзя."""
    requests = [stored(1), stored(2, status_id=PLANNED)]
    change_status = AsyncMock()

    report = await bulk_update(
        requests, RequestBulkUpdate(request_ids=[1, 2], status_id=4), change_status
    )

    assert report.updated == 2
    assert change_status.await_args.args[2] == 4
    assert change_status.await_args.kwargs["manual"] is True


@pytest.mark.asyncio
async def test_fields_and_status_together_need_editable_requests():
    """Меняем и поля, и статус: заявка в плане так не даётся — сначала о ней скажут."""
    requests = [stored(1), stored(2, status_id=PLANNED)]

    with pytest.raises(requests_service.RequestDataError, match="№2 уже «В плане»"):
        await bulk_update(
            requests, RequestBulkUpdate(request_ids=[1, 2], status_id=4, priority_id=1)
        )
