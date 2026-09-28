"""Выдача оборудования по плану и защита фактического запаса смены."""

from datetime import date
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
    result = item(need=1, limit=30, reserve=2, current=7)
    assert result.current == 7
    assert result.recommended == 7


def test_existing_stock_is_still_capped_by_transport_capacity():
    """Ошибочную старую выдачу выше нового лимита интерфейс предлагает исправить."""
    assert item(need=1, limit=5, reserve=2, current=7).recommended == 5


@pytest.mark.asyncio
async def test_plan_stock_reports_cumulative_shortage(monkeypatch):
    """Для утверждения складывается расход всех заявок маршрута, а не максимум одной."""
    assignments = [
        SimpleNamespace(
            engineer_id=7,
            request=SimpleNamespace(
                equipment=[SimpleNamespace(equipment_id=1, quantity=2)]
            ),
        ),
        SimpleNamespace(
            engineer_id=7,
            request=SimpleNamespace(
                equipment=[SimpleNamespace(equipment_id=1, quantity=2)]
            ),
        ),
        SimpleNamespace(engineer_id=None, request=SimpleNamespace(equipment=[])),
    ]
    engineer = SimpleNamespace(
        id=7,
        name="Бригада Арташкин",
        equipment_items=[SimpleNamespace(equipment_id=1, quantity=3)],
    )
    monkeypatch.setattr(
        equipment_issue.plans_repository,
        "list_plan_assignments",
        AsyncMock(return_value=assignments),
    )
    monkeypatch.setattr(
        equipment_issue, "_engineers_by_ids", AsyncMock(return_value=[engineer])
    )
    monkeypatch.setattr(equipment_issue, "_equipment_names", AsyncMock(return_value={1: "Роутер"}))

    problems = await equipment_issue.plan_stock_problems(SimpleNamespace(), SimpleNamespace(id=5))

    assert problems == ["Бригада Арташкин: «Роутер» нужно 4, выдано 3"]


@pytest.mark.asyncio
async def test_plan_stock_accepts_exact_quantity(monkeypatch):
    assignment = SimpleNamespace(
        engineer_id=7,
        request=SimpleNamespace(equipment=[SimpleNamespace(equipment_id=1, quantity=4)]),
    )
    engineer = SimpleNamespace(
        id=7,
        name="Бригада Арташкин",
        equipment_items=[SimpleNamespace(equipment_id=1, quantity=4)],
    )
    monkeypatch.setattr(
        equipment_issue.plans_repository,
        "list_plan_assignments",
        AsyncMock(return_value=[assignment]),
    )
    monkeypatch.setattr(
        equipment_issue, "_engineers_by_ids", AsyncMock(return_value=[engineer])
    )
    monkeypatch.setattr(equipment_issue, "_equipment_names", AsyncMock(return_value={1: "Роутер"}))

    assert await equipment_issue.plan_stock_problems(
        SimpleNamespace(), SimpleNamespace(id=5)
    ) == []


@pytest.mark.asyncio
async def test_more_than_the_transport_carries_is_rejected(monkeypatch):
    """Диспетчер правит числа руками — сервер всё равно проверяет их по справочнику."""
    plan = SimpleNamespace(id=5, office_id=1, plan_date=date(2026, 8, 17))
    engineer = SimpleNamespace(id=7, name="Бригада Арташкин", office_id=1, transport_id=2)
    monkeypatch.setattr(equipment_issue.plans_repository, "get_plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(
        equipment_issue.plans_repository,
        "list_plan_assignments",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        equipment_issue.equipment_repository, "capacity_map", AsyncMock(return_value={(2, 1): 5})
    )
    monkeypatch.setattr(equipment_issue, "_equipment_names", AsyncMock(return_value={1: "Роутер"}))
    monkeypatch.setattr(
        equipment_issue.engineers_repository,
        "list_engineers_in_period",
        AsyncMock(return_value=[engineer]),
    )
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
