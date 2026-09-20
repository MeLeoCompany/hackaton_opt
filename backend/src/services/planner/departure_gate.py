"""Можно ли бригаде выезжать на следующую заявку (docs/algoV2.md, шаги 7-9).

Бригада выбилась из плана, если верно любое из двух:
  - не отметила «Выехали» через departure_grace_minutes после планового начала работ;
  - с текущим отставанием к окну следующей заявки уже не успеть.
Тогда выезд закрыт: бригада ждёт нового плана, а оператор звонит и либо разрешает выезд
(клиент согласился подождать), либо пересчитывает. Выезд закрыт и пока есть неутверждённый
пересчёт — иначе бригада закрепит за собой заявку вопреки расчёту.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.config import settings

WAIT_FOR_PLAN = "Ждите нового плана: диспетчер пересчитывает маршрут"
BEHIND_SCHEDULE = "Ждите нового плана: бригада выбилась из графика"
AT_RISK = "Ждите нового плана: к заявке уже не успеть до конца окна"

# те же причины словами оператора: в приложении бригада читает про себя, в плане — диспетчер
OPERATOR_REASON = {
    WAIT_FOR_PLAN: "идёт пересчёт",
    BEHIND_SCHEDULE: "не выехала по плану",
    AT_RISK: "к заявке уже не успеть до конца окна",
}


@dataclass(frozen=True)
class DepartureCheck:
    """Разрешён ли выезд и почему нет."""

    allowed: bool
    reason: str | None = None


def check_departure(
    *,
    planned_start: datetime | None,
    departed_at: datetime | None,
    at_risk: bool,
    allowed_at: datetime | None,
    replan_pending: bool,
    now: datetime,
) -> DepartureCheck:
    """planned_start — плановое начало работ, allowed_at — оператор разрешил выезд."""
    if departed_at is not None or allowed_at is not None:
        return DepartureCheck(allowed=True)
    if replan_pending:
        return DepartureCheck(allowed=False, reason=WAIT_FOR_PLAN)
    if at_risk:
        return DepartureCheck(allowed=False, reason=AT_RISK)
    grace = timedelta(minutes=settings.departure_grace_minutes)
    if planned_start is not None and now > planned_start + grace:
        return DepartureCheck(allowed=False, reason=BEHIND_SCHEDULE)
    return DepartureCheck(allowed=True)
