"""Отставание бригады от плана по её отметкам и заявки, к которым она уже не успеет."""

from datetime import datetime, timedelta, timezone

from src.services.planner.route_delay import VisitFact, route_delay

MSK = timezone(timedelta(hours=3))


def at(hour, minute=0):
    return datetime(2026, 8, 17, hour, minute, tzinfo=MSK)


def visit(request_id, start, state="planned", window_end=None, **fact):
    return VisitFact(
        request_id=request_id,
        planned_start=start,
        duration_minutes=60,
        window_end=window_end or start + timedelta(hours=2),
        state=state,
        **fact,
    )


def test_on_schedule_no_delay():
    route = [visit(1, at(10), "done", finished_at=at(11)), visit(2, at(12))]
    assert route_delay(route, None).delay_minutes == 0


def test_late_finish_carries_to_the_rest_and_flags_missed_windows():
    route = [
        visit(1, at(10), "done", finished_at=at(12, 30)),  # закончила на 1,5 часа позже
        visit(2, at(12), window_end=at(13)),  # запас по окну час — не успеет
        visit(3, at(15), window_end=at(18)),  # запас три часа — успеет
    ]
    delay = route_delay(route, None)
    assert delay.delay_minutes == 90
    assert delay.at_risk_request_ids == [2]


def test_late_arrival_counts_and_current_visit_is_not_at_risk():
    route = [
        visit(1, at(10), "onsite", arrived_at=at(10, 40), window_end=at(10, 30)),
        visit(2, at(12)),
    ]
    delay = route_delay(route, None)
    assert delay.delay_minutes == 40
    assert delay.at_risk_request_ids == []  # бригада на месте — окно первой уже не упущено


def test_now_matters_only_for_todays_plan():
    route = [visit(1, at(10), "done", finished_at=at(11)), visit(2, at(12), window_end=at(12, 30))]
    # 13:00, а к второй ещё не выехала: отстаёт на час, окно до 12:30 упущено
    delay = route_delay(route, at(13))
    assert (delay.delay_minutes, delay.at_risk_request_ids) == (60, [2])
    # без «сейчас» (план не на сегодня) — только отметки
    assert route_delay(route, None).delay_minutes == 0


def test_cancelled_and_removed_visits_are_skipped():
    route = [
        visit(1, at(10), "cancelled"),
        visit(2, at(11), "removed"),
        visit(3, at(12), window_end=at(12, 10)),
    ]
    delay = route_delay(route, at(12, 30))
    assert (delay.delay_minutes, delay.at_risk_request_ids) == (30, [3])
