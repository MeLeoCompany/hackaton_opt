"""Офисы: старт бригады из своего офиса, проверки справочника, колонка CSV «старт_из_офиса»."""

from datetime import timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.schemas.offices import OfficeWrite
from src.services.engineers import engineers_service
from src.services.engineers.engineers_csv import (
    EngineerReferenceLookup,
    build_csv_template,
    parse_engineers_csv,
)
from src.services.offices import offices_service
from src.services.requests.requests_csv import reference_options

MOSCOW = timezone(timedelta(hours=3))
SIMFEROPOLSKY = SimpleNamespace(
    id=3, name="Югоцентр", latitude=Decimal("55.664757"), longitude=Decimal("37.615839")
)


@pytest.mark.asyncio
async def test_engineer_starting_at_office_gets_office_point(monkeypatch):
    monkeypatch.setattr(
        engineers_service.offices_repository, "get_office", AsyncMock(return_value=SIMFEROPOLSKY)
    )

    fields = await engineers_service.with_office_start(
        object(),
        {"office_id": 3, "start_at_office": True, "start_latitude": 1.0, "start_longitude": 2.0},
    )

    # клиент прислал что угодно — старт всё равно в точке офиса
    assert fields["start_latitude"] == Decimal("55.664757")
    assert fields["start_longitude"] == Decimal("37.615839")


@pytest.mark.asyncio
async def test_engineer_with_own_point_keeps_it(monkeypatch):
    get_office = AsyncMock()
    monkeypatch.setattr(engineers_service.offices_repository, "get_office", get_office)

    fields = await engineers_service.with_office_start(
        object(),
        {"office_id": 3, "start_at_office": False, "start_latitude": 55.7, "start_longitude": 37.6},
    )

    assert fields["start_latitude"] == 55.7
    get_office.assert_not_awaited()


@pytest.mark.asyncio
async def test_office_name_must_be_unique(monkeypatch):
    monkeypatch.setattr(
        offices_service.offices_repository,
        "find_office_by_name",
        AsyncMock(return_value=SIMFEROPOLSKY),
    )

    with pytest.raises(offices_service.OfficeDataError, match="уже есть"):
        await offices_service.check_name_is_free(object(), "югоцентр")
    # тот же офис под своим именем — не конфликт
    await offices_service.check_name_is_free(object(), "Югоцентр", except_id=3)


@pytest.mark.asyncio
async def test_office_with_data_cannot_be_deleted(monkeypatch):
    repository = offices_service.offices_repository
    monkeypatch.setattr(repository, "get_office", AsyncMock(return_value=SIMFEROPOLSKY))
    monkeypatch.setattr(
        repository,
        "count_usages",
        AsyncMock(return_value={"заявок": 9, "бригад": 7, "планов": 0, "учёток": 1}),
    )
    delete = AsyncMock()
    monkeypatch.setattr(repository, "delete_office", delete)

    with pytest.raises(offices_service.OfficeInUseError, match="заявок 9, бригад 7, учёток 1"):
        await offices_service.delete_office(object(), 3)
    delete.assert_not_awaited()


def test_office_needs_address_and_real_coordinates():
    with pytest.raises(ValidationError):
        OfficeWrite(name="Офис", address="", latitude=55.7, longitude=37.6)
    with pytest.raises(ValidationError):
        OfficeWrite(name="Офис", address="Москва", latitude=95.0, longitude=37.6)


REFERENCES = EngineerReferenceLookup(
    transports=reference_options([(1, "Автомобиль")]),
    skills=reference_options([(1, "Локальные работы")]),
)
HEADER = "id;имя;широта_старта;долгота_старта;транспорт;навыки;смена_начало;смена_конец"
SHIFT = "Автомобиль;Локальные работы;17.08.2026 09:00;17.08.2026 18:00"


def parse(*lines):
    return parse_engineers_csv("\n".join(lines).encode(), REFERENCES, MOSCOW)


def test_csv_start_at_office_needs_no_coordinates():
    result = parse(HEADER + ";старт_из_офиса", f"7;Бригада;;;{SHIFT};да")

    assert result.errors == []
    assert result.rows[0]["start_at_office"] is True


def test_csv_own_point_needs_coordinates():
    result = parse(HEADER + ";старт_из_офиса", f"7;Бригада;;;{SHIFT};нет")

    assert result.rows == []
    assert any("широта_старта" in message for message in result.errors)


def test_csv_start_flag_must_be_yes_or_no():
    result = parse(HEADER + ";старт_из_офиса", f"7;Бригада;55.7;37.6;{SHIFT};может быть")

    assert any("старт_из_офиса" in message for message in result.errors)


def test_csv_with_coordinates_and_no_flag_means_own_point():
    result = parse(HEADER, f"7;Бригада;55.7;37.6;{SHIFT}")

    assert result.errors == []
    assert result.rows[0]["start_at_office"] is False


def test_csv_without_coordinates_starts_at_office():
    # обычный случай: координат нет — бригада выезжает из офиса
    result = parse(HEADER, f"7;Бригада;;;{SHIFT}")

    assert result.errors == []
    assert result.rows[0]["start_at_office"] is True


def test_template_shows_start_column():
    header, *_ = build_csv_template().splitlines()

    assert header.endswith(";старт_из_офиса")
