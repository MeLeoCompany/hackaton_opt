"""Раскрытие окон использует момент исходного расчёта, а не время повторного запуска."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.services.planner import planner_loader
from src.services.planner.planner_problem import EngineerSpec, ProblemInstance, RequestSpec

MSK = timezone(timedelta(hours=3))


def test_explicit_calculation_moment_does_not_move_with_clock():
    instance = ProblemInstance(
        engineers=[EngineerSpec(1, "Бригада", 4, 540, 1380)],
        requests=[RequestSpec(10, 30, 600, 660, 1, None)],
        distance_km={},
        travel_min={},
    )
    loaded = planner_loader.LoadedDay(
        day=planner_loader.planning_day(date(2026, 8, 25)),
        office_id=1,
        instance=instance,
        requests=[SimpleNamespace(id=10)],
        engineers=[SimpleNamespace(id=1)],
        skill_names={},
        transport_names={},
    )
    calculation_at = datetime(2026, 8, 25, 12, 15, tzinfo=MSK)

    with patch.object(
        planner_loader.clock,
        "now",
        return_value=datetime(2026, 8, 25, 18, 0, tzinfo=MSK),
    ):
        widened, kept = planner_loader.widen_day(loaded, {10}, not_before=calculation_at)

    assert widened.instance.requests[0].window_start_min == 12 * 60 + 15
    assert widened.instance.requests[0].window_end_min == 23 * 60
    assert kept == set()

