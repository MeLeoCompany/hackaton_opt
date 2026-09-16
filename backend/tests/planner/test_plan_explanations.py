from types import SimpleNamespace

from planner_test_helpers import engineer, make_instance, request

from src.services.planner.planning_service import (
    SCHEDULE_REASON,
    TIME_REASON,
    assignment_explanation,
    count_urgent_assignments,
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


def test_assignment_explanation_describes_constraints_and_objective():
    assignment = SimpleNamespace(
        visit_order=2,
        request=SimpleNamespace(transport_id=1),
    )

    explanation = assignment_explanation(assignment, "Бригада 1")

    assert "Бригада 1" in explanation
    assert "квалификация подходит" in explanation
    assert "транспорт соответствует" in explanation
    assert "Позиция №2" in explanation
    assert "срочности" in explanation


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
