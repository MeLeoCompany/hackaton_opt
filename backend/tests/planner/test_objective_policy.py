import pytest

from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    objective_policy_name,
    validate_objective_order,
)


def test_default_policy_has_business_name():
    assert objective_policy_name(DEFAULT_OBJECTIVE_ORDER) == "Срочность · максимум заявок"


def test_dispatcher_may_put_crews_or_distance_right_after_priorities():
    """Ярусы приоритетов остаются первыми, дальше порядок выбирает диспетчер."""
    order = [
        ObjectiveCriterion.URGENT_REQUESTS,
        ObjectiveCriterion.ENGINEERS_USED,
        ObjectiveCriterion.ASSIGNED_REQUESTS,
        ObjectiveCriterion.TRAVEL_DISTANCE,
    ]

    assert validate_objective_order(order) == tuple(order)
    assert objective_policy_name(order) == "Срочность · минимум бригад"


@pytest.mark.parametrize(
    "order",
    [
        list(DEFAULT_OBJECTIVE_ORDER[:-1]),
        [*DEFAULT_OBJECTIVE_ORDER[:3], ObjectiveCriterion.ENGINEERS_USED],
        # уровни приоритета не первые: экономия бригад перевесила бы аварийную заявку
        [
            ObjectiveCriterion.ENGINEERS_USED,
            ObjectiveCriterion.ASSIGNED_REQUESTS,
            ObjectiveCriterion.URGENT_REQUESTS,
            ObjectiveCriterion.TRAVEL_DISTANCE,
        ],
        [
            ObjectiveCriterion.ASSIGNED_REQUESTS,
            ObjectiveCriterion.URGENT_REQUESTS,
            ObjectiveCriterion.ENGINEERS_USED,
            ObjectiveCriterion.TRAVEL_DISTANCE,
        ],
    ],
)
def test_invalid_or_dangerous_policy_is_rejected(order):
    with pytest.raises(ValueError):
        validate_objective_order(order)
