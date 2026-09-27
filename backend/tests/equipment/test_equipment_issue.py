"""Выдача оборудования по плану: items = min(ёмкость транспорта, нужно по плану + запас)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.equipment import equipment_issue


def item(*, need, limit, reserve, current=0):
    return equipment_issue._item(
        equipment_id=1, name="Роутер", need=need, limit=limit, current=current, reserve=reserve
    )


def test_issue_is_need_plus_reserve_while_it_fits():
    """Обычный случай: бригаде нужно 4 штуки, запас 2 — берёт 6."""
    assert item(need=4, limit=30, reserve=2).recommended == 6


def test_transport_limit_wins_over_need():
    """Пешеход не унесёт больше, чем влезает, сколько бы заявок ему ни досталось."""
    assert item(need=12, limit=5, reserve=2).recommended == 5


def test_brigade_without_such_requests_still_takes_the_reserve():
    """x0 = 0: запас всё равно выдаём — днём появятся новые заявки."""
    assert item(need=0, limit=30, reserve=2).recommended == 2


def test_transport_that_does_not_carry_it_gets_nothing():
    """Нулевая ёмкость — это «этим транспортом не возят», запас её не обходит."""
    assert item(need=3, limit=0, reserve=2).recommended == 0


def test_preview_keeps_what_is_already_issued():
    """«Сейчас» показывает запас смены: видно, что именно изменится при утверждении."""
    assert item(need=1, limit=30, reserve=2, current=7).current == 7


@pytest.mark.asyncio
async def test_more_than_the_transport_carries_is_rejected(monkeypatch):
    """Диспетчер правит числа руками — сервер всё равно проверяет их по справочнику."""
    plan = SimpleNamespace(id=5, office_id=1)
    engineer = SimpleNamespace(id=7, name="Бригада Арташкин", office_id=1, transport_id=2)
    monkeypatch.setattr(equipment_issue.plans_repository, "get_plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(
        equipment_issue.equipment_repository, "capacity_map", AsyncMock(return_value={(2, 1): 5})
    )
    monkeypatch.setattr(equipment_issue, "_equipment_names", AsyncMock(return_value={1: "Роутер"}))
    session = SimpleNamespace(get=AsyncMock(return_value=engineer), commit=AsyncMock())
    written = []
    monkeypatch.setattr(
        equipment_issue.engineers_repository,
        "set_equipment",
        lambda _engineer, quantities: written.append(quantities),
    )

    payload = [SimpleNamespace(engineer_id=7, items=[SimpleNamespace(equipment_id=1, quantity=99)])]
    with pytest.raises(equipment_issue.IssueDataError, match="увезёт 5"):
        await equipment_issue.apply(session, 5, payload, office_id=1)

    assert session.commit.await_count == 0
