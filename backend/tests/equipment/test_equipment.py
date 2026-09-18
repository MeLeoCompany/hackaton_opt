"""Оборудование: справочник и требование заявки, в том числе в CSV."""

from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models import EngineerEquipment
from src.repositories.engineers import engineers_repository
from src.services.engineers.engineers_csv import EngineerReferenceLookup, parse_engineers_csv
from src.services.equipment import equipment_service
from src.services.requests.requests_csv import (
    ReferenceLookup,
    WorkTypeNorm,
    build_csv_template,
    parse_requests_csv,
    reference_options,
)

MOSCOW = timezone(timedelta(hours=3))
ROUTER = SimpleNamespace(id=1, name="Роутер", description="")


@pytest.mark.asyncio
async def test_equipment_required_by_requests_cannot_be_deleted(monkeypatch):
    repository = equipment_service.equipment_repository
    monkeypatch.setattr(repository, "get_equipment", AsyncMock(return_value=ROUTER))
    monkeypatch.setattr(repository, "count_requests", AsyncMock(return_value=4))
    monkeypatch.setattr(repository, "count_engineers", AsyncMock(return_value=0))
    delete = AsyncMock()
    monkeypatch.setattr(repository, "delete_equipment", delete)

    with pytest.raises(equipment_service.EquipmentInUseError, match=r"требуется в заявках \(4\)"):
        await equipment_service.delete_equipment(object(), 1)
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_equipment_name_must_be_unique(monkeypatch):
    monkeypatch.setattr(
        equipment_service.equipment_repository,
        "find_equipment_by_name",
        AsyncMock(return_value=ROUTER),
    )

    with pytest.raises(equipment_service.EquipmentDataError, match="уже есть"):
        await equipment_service.check_name_is_free(object(), "роутер")
    await equipment_service.check_name_is_free(object(), "Роутер", except_id=1)


REFERENCES = ReferenceLookup(
    skills=reference_options([(1, "Локальные работы")]),
    priorities=reference_options([(2, "Обычная")]),
    transports=reference_options([(1, "Автомобиль")]),
    work_types=reference_options([(4, "Локальная заявка / ремонт у клиента")]),
    work_type_norms={4: WorkTypeNorm(skill_id=1, work_minutes=30)},
    equipment=reference_options([(1, "Роутер"), (2, "ТВ-приставка")]),
)
HEADER = "id;адрес;широта;долгота;тип_работ;окно_начало;окно_конец;приоритет"
ROW = "7;Москва;55.7;37.6;4;17.08.2026 10:00;17.08.2026 12:00;Обычная"


def parse(*lines):
    return parse_requests_csv("\n".join(lines).encode(), REFERENCES, MOSCOW)


def test_csv_equipment_by_name():
    result = parse(HEADER + ";оборудование", ROW + ";тв-приставка")

    assert result.errors == []
    assert result.rows[0]["equipment"] == {2: 1}


def test_csv_several_equipment_types_at_once():
    result = parse(HEADER + ";оборудование", ROW + ';"Роутер: 2, 2"')

    assert result.errors == []
    # количество через двоеточие, без него — одна штука
    assert result.rows[0]["equipment"] == {1: 2, 2: 1}


def test_csv_same_equipment_twice_is_an_error():
    result = parse(HEADER + ";оборудование", ROW + ';"Роутер, роутер"')

    assert result.rows == []
    assert any("дважды" in message for message in result.errors)


def test_csv_empty_equipment_clears_requirement():
    result = parse(HEADER + ";оборудование", ROW + ";")

    assert result.rows[0]["equipment"] == {}


def test_csv_without_equipment_column_leaves_requirement_alone():
    result = parse(HEADER, ROW)

    # поля нет вовсе — у существующей заявки требование не изменится
    assert "equipment" not in result.rows[0]


def test_csv_unknown_equipment_is_an_error():
    result = parse(HEADER + ";оборудование", ROW + ";Спутниковая тарелка")

    assert result.rows == []
    assert any("оборудование" in message for message in result.errors)


def test_template_shows_equipment_column():
    header, example, *_ = build_csv_template().splitlines()

    assert header.endswith(";оборудование")
    assert example.endswith(';"Роутер: 2, ТВ-приставка"')


@pytest.mark.asyncio
async def test_equipment_carried_by_engineers_cannot_be_deleted(monkeypatch):
    repository = equipment_service.equipment_repository
    monkeypatch.setattr(repository, "get_equipment", AsyncMock(return_value=ROUTER))
    monkeypatch.setattr(repository, "count_requests", AsyncMock(return_value=0))
    monkeypatch.setattr(repository, "count_engineers", AsyncMock(return_value=2))

    with pytest.raises(equipment_service.EquipmentInUseError, match=r"есть у бригад \(2\)"):
        await equipment_service.delete_equipment(object(), 1)


ENGINEER_REFERENCES = EngineerReferenceLookup(
    transports=reference_options([(1, "Автомобиль")]),
    skills=reference_options([(1, "Локальные работы")]),
    equipment=reference_options([(1, "Роутер"), (2, "ТВ-приставка")]),
)
ENGINEER_HEADER = "id;имя;широта_старта;долгота_старта;транспорт;навыки;смена_начало;смена_конец"
ENGINEER_ROW = "7;Бригада;55.7;37.6;Автомобиль;Локальные работы;17.08.2026 09:00;17.08.2026 18:00"


def parse_engineers(*lines):
    return parse_engineers_csv("\n".join(lines).encode(), ENGINEER_REFERENCES, MOSCOW)


def test_engineer_csv_equipment_with_quantities():
    result = parse_engineers(
        ENGINEER_HEADER + ";оборудование", ENGINEER_ROW + ';"Роутер: 3, ТВ-приставка"'
    )

    assert result.errors == []
    # без количества — одна штука
    assert result.rows[0]["equipment"] == {1: 3, 2: 1}


def test_engineer_csv_bad_quantity_is_an_error():
    result = parse_engineers(ENGINEER_HEADER + ";оборудование", ENGINEER_ROW + ';"Роутер: ноль"')

    assert result.rows == []
    assert any("количество" in message for message in result.errors)


def test_engineer_csv_without_equipment_column_keeps_stock():
    result = parse_engineers(ENGINEER_HEADER, ENGINEER_ROW)

    assert "equipment" not in result.rows[0]


def test_engineer_stock_is_changed_in_place():
    engineer = SimpleNamespace(
        equipment_items=[
            EngineerEquipment(engineer_id=7, equipment_id=1, quantity=3),
            EngineerEquipment(engineer_id=7, equipment_id=2, quantity=1),
        ]
    )
    router = engineer.equipment_items[0]

    engineers_repository.set_equipment(engineer, {1: 5, 3: 2})

    # та же строка с новым количеством: иначе удаление и вставка одного ключа в одной
    # транзакции упрутся в первичный ключ
    assert engineer.equipment_items[0] is router
    assert {item.equipment_id: item.quantity for item in engineer.equipment_items} == {1: 5, 3: 2}
