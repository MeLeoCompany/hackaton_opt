"""Отставание бригады от утверждённого плана — по её отметкам в мобильном приложении.

Смотрим последнюю точку, где известны и план, и факт:
- выполненная заявка: закончила позже плана — на столько и отстаёт;
- заявка, на которой бригада сейчас: прибыла позже планового начала работ — отстаёт на это;
  если план на сегодня и плановое окончание уже прошло — не меньше, чем на «сейчас − окончание»;
- заявка, к которой бригада едет или ещё не выехала (первая незакрытая): отставание прошлой
  точки сохраняется, а если план на сегодня и плановое начало уже прошло — не меньше
  «сейчас − начало».
«Сейчас» учитывается только у плана на сегодня: у прошлого и будущего дня — только отметки.

Дальше отставание переносится на оставшиеся заявки маршрута как есть (без поправки на
ожидание: оценка с запасом). Заявка под угрозой, если с таким отставанием работу уже не
начать до конца её окна (отставание больше запаса по окну).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

CLOSED = ("done", "cancelled", "removed")


@dataclass
class VisitFact:
    request_id: int
    planned_start: datetime
    duration_minutes: int
    window_end: datetime
    state: str  # done | cancelled | removed | moving | onsite | planned
    arrived_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class RouteDelay:
    delay_minutes: int
    at_risk_request_ids: list[int]


def visit_state(status_code: str, removed: bool, arrived_at: datetime | None) -> str:
    if removed:
        return "removed"
    if status_code in ("done", "cancelled"):
        return status_code
    if status_code == "en_route":
        return "moving"
    if status_code == "in_progress":
        return "onsite" if arrived_at is not None else "moving"
    return "planned"


def route_delay(visits: list[VisitFact], now: datetime | None) -> RouteDelay:
    """Отставание маршрута и заявки под угрозой; visits — по порядку маршрута."""
    delay = timedelta(0)
    current = None  # индекс первой незакрытой заявки
    for index, visit in enumerate(visits):
        planned_end = visit.planned_start + timedelta(minutes=visit.duration_minutes)
        if visit.state == "done":
            if visit.finished_at is not None:
                delay = max(timedelta(0), visit.finished_at - planned_end)
            continue
        if visit.state in CLOSED:
            continue
        current = index
        if visit.state == "onsite" and visit.arrived_at is not None:
            delay = max(timedelta(0), visit.arrived_at - visit.planned_start)
            if now is not None:
                delay = max(delay, now - planned_end)
        elif now is not None:
            delay = max(delay, now - visit.planned_start)
        break

    minutes = int(delay.total_seconds() // 60)
    if current is None or minutes <= 0:
        return RouteDelay(delay_minutes=max(minutes, 0), at_risk_request_ids=[])

    # на заявке, где бригада уже на месте, окно не упущено — под угрозой только следующие
    first_open = current + 1 if visits[current].state == "onsite" else current
    at_risk = [
        visit.request_id
        for visit in visits[first_open:]
        if visit.state in ("planned", "moving") and visit.planned_start + delay > visit.window_end
    ]
    return RouteDelay(delay_minutes=minutes, at_risk_request_ids=at_risk)
