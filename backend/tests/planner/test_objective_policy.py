import pytest

from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    objective_policy_name,
    validate_objective_order,
)


def test_default_policy_has_business_name():
    assert objective_policy_name(DEFAULT_OBJECTIVE_ORDER) == "Срочность · минимум бригад"


@pytest.mark.parametrize(
    "order",
    [
        list(DEFAULT_OBJECTIVE_ORDER[:-1]),
        [*DEFAULT_OBJECTIVE_ORDER[:3], ObjectiveCriterion.ENGINEERS_USED],
        [
            ObjectiveCriterion.ENGINEERS_USED,
            ObjectiveCriterion.ASSIGNED_REQUESTS,
            ObjectiveCriterion.URGENT_REQUESTS,
            ObjectiveCriterion.TRAVEL_DISTANCE,
        ],
    ],
)
def test_invalid_or_dangerous_policy_is_rejected(order):
    with pytest.raises(ValueError):
        validate_objective_order(order)
