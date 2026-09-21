"""Параметры расчёта: сколько cuOpt ищет решение и что из этого следует (db/init/040)."""

import pytest
from pydantic import ValidationError

from src.schemas.system import SolverParams


def test_small_day_gets_the_base_time_and_big_one_grows_to_the_cap():
    """Время поиска — это и есть «точность»: маленькому дню хватает базового."""
    params = SolverParams(
        time_limit_seconds=2, seconds_per_location=0.2, free_locations=20, max_time_limit_seconds=20
    )

    assert params.limit_for(7) == 2
    assert params.limit_for(50) == 6  # 30 точек сверх бесплатных по 0.2 с
    assert params.limit_for(1000) == 20


def test_maximum_below_base_is_rejected():
    with pytest.raises(ValidationError, match="максимальное время поиска"):
        SolverParams(time_limit_seconds=30, max_time_limit_seconds=10)


@pytest.mark.parametrize(
    "field", ["time_limit_seconds", "max_time_limit_seconds", "distance_weight", "transit_attempts"]
)
def test_zero_and_negative_values_are_rejected(field):
    with pytest.raises(ValidationError):
        SolverParams(**{field: 0})
