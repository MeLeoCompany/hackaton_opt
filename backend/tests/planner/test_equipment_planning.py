"""Оборудование ограничивает весь маршрут и корректно переживает пересчёт дня."""

from datetime import date
from types import SimpleNamespace

from planner_test_helpers import engineer, make_instance, request

from src.models import RequestStatusId
from src.services.planner import planner_loader, replan_service


def assignment(status_id: int, quantity: int):
    return SimpleNamespace(
        request=SimpleNamespace(
            status_id=status_id,
            equipment=[SimpleNamespace(equipment_id=7, quantity=quantity)],
        )
    )


def test_replan_counts_done_and_started_but_not_cancelled_equipment():
    consumed = replan_service.consumed_equipment(
        {
            1: [
                assignment(RequestStatusId.DONE, 2),
                assignment(RequestStatusId.EN_ROUTE, 1),
                assignment(RequestStatusId.CANCELLED, 5),
            ]
        }
    )

    assert consumed == {1: {7: 3}}


def test_consumed_equipment_reduces_stock_and_rebuilds_compatibility():
    instance = make_instance(
        engineers=[engineer(1, equipment={7: 3})],
        requests=[request(10, skill=1, window=("10:00", "12:00"), equipment={7: 2})],
        skills={1: {1}},
    )
    loaded = planner_loader.LoadedDay(
        day=planner_loader.planning_day(date(2026, 8, 17)),
        office_id=1,
        instance=instance,
        requests=[SimpleNamespace(id=10)],
        engineers=[SimpleNamespace(id=1, skills=[SimpleNamespace(id=1)])],
        skill_names={1: "Монтаж"},
        transport_names={1: "Автомобиль"},
        equipment_names={7: "Роутер"},
    )

    adjusted = planner_loader.consume_equipment(loaded, {1: {7: 2}})

    assert adjusted.instance.engineers[0].equipment_capacity == {7: 1}
    assert adjusted.instance.candidates(0) == []
    # Исходный снимок задачи не меняется ни в запасах, ни в общей mutable-матрице.
    assert loaded.instance.engineers[0].equipment_capacity == {7: 3}
    assert loaded.instance.candidates(0) == [0]
    assert adjusted.instance.compatible is not loaded.instance.compatible


def test_initial_plan_uses_transport_capacity_before_equipment_is_issued():
    engineer_row = SimpleNamespace(
        transport_id=4,
        equipment_items=[],
    )
    equipment = [SimpleNamespace(id=7), SimpleNamespace(id=8)]

    capacity = planner_loader._engineer_equipment_capacity(
        engineer_row,
        equipment,
        {(4, 7): 6, (4, 8): 0},
    )

    assert capacity == {7: 6}


def test_replan_uses_only_the_actual_shift_stock():
    engineer_row = SimpleNamespace(
        transport_id=4,
        equipment_items=[SimpleNamespace(equipment_id=7, quantity=3)],
    )

    capacity = planner_loader._engineer_equipment_capacity(
        engineer_row,
        [SimpleNamespace(id=7)],
        None,
    )

    assert capacity == {7: 3}
