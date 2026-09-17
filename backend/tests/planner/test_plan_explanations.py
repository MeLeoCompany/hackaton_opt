from types import SimpleNamespace

from planner_test_helpers import engineer, make_instance, request

from datetime import datetime, timedelta, timezone

from src.services.planner.planning_service import (
    SCHEDULE_REASON,
    TIME_REASON,
    candidate_engineers_by_request,
    count_urgent_assignments,
    to_plan_visit,
    unassigned_reason,
)


def loaded_day(instance):
    return SimpleNamespace(instance=instance)


def test_unassigned_reason_distinguishes_impossible_first_visit():
    instance = make_instance(
        engineers=[engineer(1, shift=("09:00", "18:00"))],
        requests=[request(10, skill=1, window=("17:30", "18:00"), duration=60)],
        skills={1: {1}},
    )

    assert unassigned_reason(loaded_day(instance), 0) == TIME_REASON


def test_unassigned_reason_reports_conflict_when_request_fits_separately():
    instance = make_instance(
        engineers=[engineer(1)],
        requests=[request(10, skill=1, window=("10:00", "12:00"))],
        skills={1: {1}},
    )

    assert unassigned_reason(loaded_day(instance), 0) == SCHEDULE_REASON


def test_visit_keeps_facts_of_its_own_place_in_route():
    """Из этих чисел интерфейс объясняет визит: когда освободился, сколько осталось запаса."""
    day = datetime(2026, 8, 17, tzinfo=timezone.utc)
    assignment = SimpleNamespace(
        visit_order=2,
        planned_arrival_time=day + timedelta(hours=10),  # начало работ 10:00
        request=SimpleNamespace(
            id=10,
            address="Ленина, 1",
            latitude=55.7,
            longitude=37.6,
            window_start=day + timedelta(hours=9),
            window_end=day + timedelta(hours=12),  # запас до закрытия окна 2 часа
            duration_minutes=60,
            priority_id=1,
            transport_id=None,
        ),
    )

    visit = to_plan_visit(
        assignment,
        available_from=day + timedelta(hours=9, minutes=30),
        shift_end=day + timedelta(hours=18),  # после работы до конца смены 7 часов
        candidate_engineers=3,
    )

    assert visit.available_from == day + timedelta(hours=9, minutes=30)
    assert visit.window_slack_minutes == 120
    assert visit.shift_slack_minutes == 420
    assert visit.candidate_engineers == 3


def test_candidate_engineers_counted_by_skill_and_transport():
    snapshot = {
        "requests": {
            "10": {"id": 10, "skill_id": 1, "transport_id": None},
            "11": {"id": 11, "skill_id": 1, "transport_id": 2},
            "12": {"id": 12, "skill_id": 3, "transport_id": None},
        },
        "engineers": {
            "1": {"skill_ids": [1, 2], "transport_id": 1},
            "2": {"skill_ids": [1], "transport_id": 2},
        },
    }

    counts = candidate_engineers_by_request(snapshot)

    assert counts == {10: 2, 11: 1, 12: 0}


def test_urgent_assignments_are_counted_from_frozen_snapshot():
    snapshot = {
        "requests": {
            "10": {"is_urgent": True},
            "20": {"is_urgent": False},
            "30": {"is_urgent": True},
        }
    }

    assert count_urgent_assignments(snapshot, {10, 20}) == 1
    assert count_urgent_assignments(snapshot, {10, 30}) == 2


def test_old_snapshot_without_urgency_returns_unknown_count():
    assert count_urgent_assignments({"requests": {"10": {}}}, {10}) is None
