"""Перемотка системного времени: её видят все расчёты, которые спрашивают «сейчас»."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core import clock
from src.schemas.system import SystemTimeWrite
from src.services.system import system_service


@pytest.fixture(autouse=True)
def reset_clock():
    clock.set_offset(timedelta(0))
    yield
    clock.set_offset(timedelta(0))


def stored(offset_seconds=0):
    return SimpleNamespace(
        id=1,
        offset_seconds=offset_seconds,
        updated_at=datetime(2026, 9, 20, tzinfo=UTC),
        updated_by=None,
    )


def with_row(row):
    return patch.object(
        system_service.system_repository, "get_system_time", AsyncMock(return_value=row)
    )


@pytest.mark.asyncio
async def test_clock_moves_to_the_requested_moment():
    row = stored()
    session = SimpleNamespace(commit=AsyncMock(), get=AsyncMock(return_value=None))
    target = clock.real_now() + timedelta(days=2, hours=3)

    with with_row(row):
        result = await system_service.set_time(session, SystemTimeWrite(now=target), user_id=7)

    # сдвиг сохранён и применён к часам
    assert abs(row.offset_seconds - 2 * 24 * 3600 - 3 * 3600) <= 1
    assert row.updated_by == 7
    assert abs((clock.now() - target).total_seconds()) <= 1
    assert abs((result.now - target).total_seconds()) <= 1


@pytest.mark.asyncio
async def test_zero_offset_returns_real_time():
    row = stored(offset_seconds=3600)
    session = SimpleNamespace(commit=AsyncMock(), get=AsyncMock(return_value=None))

    with with_row(row):
        result = await system_service.set_time(session, SystemTimeWrite(offset_seconds=0))

    assert row.offset_seconds == 0
    assert clock.offset() == timedelta(0)
    assert abs((result.now - clock.real_now()).total_seconds()) <= 1


@pytest.mark.parametrize("seconds", [400 * 24 * 3600, -400 * 24 * 3600])
@pytest.mark.asyncio
async def test_too_big_jump_is_rejected(seconds):
    """Год назад — чтобы открыть демо-данные прошлых дней, дальше уже незачем."""
    session = SimpleNamespace(commit=AsyncMock(), get=AsyncMock(return_value=None))
    with (
        with_row(stored()),
        pytest.raises(system_service.SystemTimeError, match="на год назад или вперёд"),
    ):
        await system_service.set_time(session, SystemTimeWrite(offset_seconds=seconds))


@pytest.mark.asyncio
async def test_either_moment_or_offset_is_required():
    session = SimpleNamespace(commit=AsyncMock(), get=AsyncMock(return_value=None))
    with (
        with_row(stored()),
        pytest.raises(system_service.SystemTimeError, match="либо сдвиг"),
    ):
        await system_service.set_time(session, SystemTimeWrite())


@pytest.mark.asyncio
async def test_saved_offset_is_restored_on_startup():
    with with_row(stored(offset_seconds=7200)):
        await system_service.load_offset(object())

    assert clock.offset() == timedelta(hours=2)


def test_password_is_hidden_in_connection_string():
    hidden = system_service.hidden_password(
        "postgresql+asyncpg://routing:secret@postgres:5432/routing"
    )

    assert hidden == "postgresql+asyncpg://routing:***@postgres:5432/routing"
    assert "secret" not in hidden
