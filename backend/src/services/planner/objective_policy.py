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

SERVICE_CRITERIA = {
    ObjectiveCriterion.URGENT_REQUESTS,
    ObjectiveCriterion.ASSIGNED_REQUESTS,
}
RESOURCE_CRITERIA = {
    ObjectiveCriterion.ENGINEERS_USED,
    ObjectiveCriterion.TRAVEL_DISTANCE,
}


def validate_objective_order(
    criteria: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
) -> tuple[ObjectiveCriterion, ...]:
    """Запрещает неполные, повторные и вырожденные политики."""
    order = tuple(criteria)
    if len(order) != 4 or set(order) != set(ObjectiveCriterion):
        raise ValueError("каждый критерий оптимизации должен быть указан ровно один раз")
    if set(order[:2]) != SERVICE_CRITERIA or set(order[2:]) != RESOURCE_CRITERIA:
        raise ValueError(
            "сначала должны идти срочность и количество заявок, затем исполнители и пробег"
        )
    return order


def objective_policy_name(
    criteria: list[ObjectiveCriterion] | tuple[ObjectiveCriterion, ...],
) -> str:
    order = validate_objective_order(criteria)
    service = "Срочность" if order[0] is ObjectiveCriterion.URGENT_REQUESTS else "Максимум заявок"
    resource = (
        "минимум бригад" if order[2] is ObjectiveCriterion.ENGINEERS_USED else "минимум пробега"
    )
    return f"{service} · {resource}"
