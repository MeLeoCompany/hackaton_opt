"""Одна бригада — одна смена за раз: пересечения не даём завести."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.engineers import EngineerCreate
from src.services.engineers import engineers_service

MOSCOW = timezone(timedelta(hours=3))

PAYLOAD = EngineerCreate(
    brigade_id=3,
    start_latitude=55.75,
    start_longitude=37.62,
    shift_start="2026-08-17T09:00:00+03:00",
    shift_end="2026-08-17T18:00:00+03:00",
    transport_id=1,
    skill_ids=[1],
)


def shift(engineer_id, start_hour, end_hour):
    return SimpleNamespace(
        id=engineer_id,
        name="Бригада Соколов",
        shift_start=datetime(2026, 8, 17, start_hour, tzinfo=MOSCOW),
        shift_end=datetime(2026, 8, 17, end_hour, tzinfo=MOSCOW),
    )


def with_shifts(shifts):
    return patch.object(
        engineers_service.engineers_repository,
        "list_brigade_shifts",
        AsyncMock(return_value=shifts),
    )


@pytest.mark.asyncio
async def test_second_shift_of_same_brigade_is_rejected():
    with (
        with_shifts([shift(5, 8, 20)]),
        pytest.raises(engineers_service.EngineerDataError) as caught,
    ):
        await engineers_service.check_brigade_is_free(None, PAYLOAD)

    message = caught.value.messages[0]
    assert "Бригада Соколов" in message
    assert "17.08.2026 08:00–20:00" in message


@pytest.mark.asyncio
async def test_own_shift_does_not_block_editing():
    # правим ту же смену — сама себе она не мешает
    with with_shifts([shift(5, 9, 18)]):
        await engineers_service.check_brigade_is_free(None, PAYLOAD, engineer_id=5)


@pytest.mark.asyncio
async def test_shift_on_another_day_is_fine():
    # репозиторий отбирает только пересекающиеся смены — других у бригады не нашлось
    with with_shifts([]):
        await engineers_service.check_brigade_is_free(None, PAYLOAD)


@pytest.mark.asyncio
async def test_csv_rows_with_two_shifts_of_one_brigade():
    values = {
        "brigade_id": 3,
        "name": "Бригада Соколов",
        "shift_start": datetime(2026, 8, 17, 9, tzinfo=MOSCOW),
        "shift_end": datetime(2026, 8, 17, 18, tzinfo=MOSCOW),
    }
    file_shifts = {}
    with with_shifts([]):
        assert (
            await engineers_service.brigade_shift_problems(
                None, values, file_shifts, engineer_id=None
            )
            == []
        )
        problems = await engineers_service.brigade_shift_problems(
            None, values, file_shifts, engineer_id=None
        )

    assert "в файле у бригады две смены сразу" in problems[0]
