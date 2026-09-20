"""Когда бригаде нельзя выезжать: выбилась из графика или идёт пересчёт."""

from datetime import UTC, datetime, timedelta

from src.services.planner.departure_gate import check_departure

PLANNED = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def gate(**changes):
    values = {
        "planned_start": PLANNED,
        "departed_at": None,
        "at_risk": False,
        "allowed_at": None,
        "replan_pending": False,
        "now": PLANNED,
    }
    return check_departure(**{**values, **changes})


def test_on_schedule_brigade_departs():
    assert gate().allowed is True


def test_small_delay_is_within_the_grace_period():
    assert gate(now=PLANNED + timedelta(minutes=9)).allowed is True


def test_brigade_that_missed_the_grace_period_waits_for_the_plan():
    check = gate(now=PLANNED + timedelta(minutes=11))

    assert check.allowed is False
    assert "выбилась из графика" in check.reason


def test_request_that_cannot_be_served_in_time_blocks_departure():
    assert gate(at_risk=True).allowed is False


def test_unapproved_replan_blocks_departure():
    check = gate(replan_pending=True)

    assert check.allowed is False
    assert "пересчитывает" in check.reason


def test_operator_can_let_the_brigade_go():
    allowed = gate(now=PLANNED + timedelta(hours=2), at_risk=True, allowed_at=PLANNED)

    assert allowed.allowed is True


def test_departed_brigade_is_not_blocked_anymore():
    assert gate(departed_at=PLANNED, at_risk=True, replan_pending=True).allowed is True
