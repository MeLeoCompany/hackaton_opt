"""Править и удалять можно только «Новую» заявку; отменённую не возвращают, а копируют."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.local_day import local_timezone
from src.models import RequestStatusId
from src.schemas.requests import RequestWrite
from src.services.requests import requests_service

NEW, PLANNED, CANCELLED = RequestStatusId.NEW, RequestStatusId.PLANNED, RequestStatusId.CANCELLED
NAMES = {NEW: "Новая", PLANNED: "В плане", CANCELLED: "Отменена"}


def stored(status_id, request_id=5):
    return SimpleNamespace(
        id=request_id,
        status_id=status_id,
        status=SimpleNamespace(name=NAMES[status_id]),
        address="Ленина, 1",
        latitude=Decimal("55.7"),
        longitude=Decimal("37.6"),
        duration_minutes=60,
        window_start=datetime(2026, 8, 17, 7, tzinfo=UTC),
        window_end=datetime(2026, 8, 17, 9, tzinfo=UTC),
        priority_id=1,
        skill_id=2,
        transport_id=None,
        work_type_id=1,
        equipment=[SimpleNamespace(equipment_id=1, quantity=2)],
    )


def test_only_new_request_is_editable():
    assert requests_service.not_editable_reason(stored(NEW)) is None
    assert "менять её нельзя" in requests_service.not_editable_reason(stored(PLANNED))
    assert "сделайте её копию" in requests_service.not_editable_reason(stored(CANCELLED))


@pytest.mark.asyncio
async def test_request_in_plan_cannot_be_edited():
    payload = RequestWrite(
        address="Другой адрес",
        latitude=55.7,
        longitude=37.6,
        window_start=datetime(2026, 8, 17, 7, tzinfo=UTC),
        window_end=datetime(2026, 8, 17, 9, tzinfo=UTC),
        priority_id=1,
    )
    with (
        patch.object(requests_service, "get_request", AsyncMock(return_value=stored(PLANNED))),
        pytest.raises(requests_service.RequestDataError, match="уже «В плане»:"),
    ):
        await requests_service.update_request(object(), 5, payload, office_id=1)


@pytest.mark.asyncio
async def test_cancelled_request_is_copied_into_a_new_one_with_the_same_data():
    create = AsyncMock(return_value=SimpleNamespace(id=6))
    with (
        patch.object(requests_service, "get_request", AsyncMock(return_value=stored(CANCELLED))),
        patch.object(requests_service, "create_request", create),
    ):
        copy = await requests_service.duplicate_request(object(), 5, office_id=1, user_id=3)

    assert copy.id == 6
    payload = create.call_args.args[1]
    assert (payload.id, payload.address, payload.duration_minutes) == (None, "Ленина, 1", 60)
    assert [(item.equipment_id, item.quantity) for item in payload.equipment] == [(1, 2)]
    assert create.call_args.kwargs["comment"] == "Копия отменённой заявки №5"


@pytest.mark.asyncio
async def test_only_cancelled_request_is_copied():
    with (
        patch.object(requests_service, "get_request", AsyncMock(return_value=stored(PLANNED))),
        pytest.raises(requests_service.RequestDataError, match="только отменённую"),
    ):
        await requests_service.duplicate_request(object(), 5, office_id=1)


@pytest.mark.asyncio
async def test_copy_can_be_moved_to_another_day():
    # окно 10:00–12:00 по Москве переезжает на другой день тем же временем суток
    create = AsyncMock(return_value=SimpleNamespace(id=7))
    with (
        patch.object(requests_service, "get_request", AsyncMock(return_value=stored(CANCELLED))),
        patch.object(requests_service, "create_request", create),
    ):
        await requests_service.duplicate_request(
            object(), 5, office_id=1, user_id=3, plan_date=date(2026, 9, 21)
        )

    payload = create.call_args.args[1]
    moscow = local_timezone()
    assert payload.window_start.astimezone(moscow).strftime("%d.%m.%Y %H:%M") == "21.09.2026 10:00"
    assert payload.window_end.astimezone(moscow).strftime("%d.%m.%Y %H:%M") == "21.09.2026 12:00"
    assert (
        create.call_args.kwargs["comment"] == "Копия отменённой заявки №5 с переносом на 21.09.2026"
    )


@pytest.mark.asyncio
async def test_only_new_request_can_be_deleted():
    for status_id in (PLANNED, CANCELLED):
        with (
            patch.object(
                requests_service, "get_request", AsyncMock(return_value=stored(status_id))
            ),
            pytest.raises(requests_service.RequestInUseError, match="Удалять можно только «Новые»"),
        ):
            await requests_service.delete_request(object(), 5, office_id=1)


@pytest.mark.asyncio
async def test_new_request_without_plans_is_deleted():
    session = SimpleNamespace(commit=AsyncMock())
    delete = AsyncMock()
    with (
        patch.object(requests_service, "get_request", AsyncMock(return_value=stored(NEW))),
        patch.object(
            requests_service.requests_repository,
            "count_request_usages",
            AsyncMock(return_value=(0, 0)),
        ),
        patch.object(requests_service.requests_repository, "delete_request", delete),
    ):
        await requests_service.delete_request(session, 5, office_id=1)

    assert delete.await_count == 1
