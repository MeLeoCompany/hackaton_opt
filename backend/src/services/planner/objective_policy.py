"""Безопасные лексикографические политики оптимизации плана."""

from enum import Enum


class ObjectiveCriterion(str, Enum):
    URGENT_REQUESTS = "urgent_requests"
    ASSIGNED_REQUESTS = "assigned_requests"
    ENGINEERS_USED = "engineers_used"
    TRAVEL_DISTANCE = "travel_distance"


DEFAULT_OBJECTIVE_ORDER = (
    ObjectiveCriterion.URGENT_REQUESTS,
    ObjectiveCriterion.ASSIGNED_REQUESTS,
    ObjectiveCriterion.ENGINEERS_USED,
    ObjectiveCriterion.TRAVEL_DISTANCE,
)

# что диспетчер ставит после приоритетов: максимум заявок, меньше бригад или меньше пробега
NEXT_GOAL_NAMES = {
    ObjectiveCriterion.ASSIGNED_REQUESTS: "максимум заявок",
    ObjectiveCriterion.ENGINEERS_USED: "минимум бригад",
    ObjectiveCriterion.TRAVEL_DISTANCE: "минимум пробега",
}


def validate_objective_order(
    criteria: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
) -> tuple[ObjectiveCriterion, ...]:
    """Запрещает неполные, повторные и вырожденные политики.

    Ярусы приоритетов (аварии, обещания, перенесённые) всегда первые: без них экономия бригад
    или пробега перевесила бы аварийную заявку. Порядок трёх остальных целей выбирает диспетчер.
    """
    order = tuple(criteria)
    if len(order) != 4 or set(order) != set(ObjectiveCriterion):
        raise ValueError("каждый критерий оптимизации должен быть указан ровно один раз")
    if order[0] is not ObjectiveCriterion.URGENT_REQUESTS:
        raise ValueError("уровни приоритета заявок всегда идут первыми")
    return order


def objective_policy_name(
    criteria: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
) -> str:
    order = validate_objective_order(criteria)
    return f"Срочность · {NEXT_GOAL_NAMES[order[1]]}"
