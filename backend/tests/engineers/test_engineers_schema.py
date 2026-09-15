"""Проверки полей исполнителя — без БД."""

import pytest
from pydantic import ValidationError

from src.schemas.engineers import EngineerCreate

VALID = {
    "name": "Бригада Тестовая",
    "start_latitude": 55.75,
    "start_longitude": 37.62,
    "shift_start": "2026-08-17T09:00:00+03:00",
    "shift_end": "2026-08-17T21:00:00+03:00",
    "transport_id": 1,
    "skill_ids": [1, 2],
}


def errors_for(**changes):
    with pytest.raises(ValidationError) as caught:
        EngineerCreate(**{**VALID, **changes})
    return str(caught.value)


def test_valid_engineer_without_id():
    engineer = EngineerCreate(**VALID)

    assert engineer.id is None
    assert engineer.skill_ids == [1, 2]


def test_needs_at_least_one_skill():
    assert "skill_ids" in errors_for(skill_ids=[])


def test_no_more_than_three_skills():
    assert "skill_ids" in errors_for(skill_ids=[1, 2, 3, 4])


def test_skills_must_not_repeat():
    assert "навыки не должны повторяться" in errors_for(skill_ids=[2, 2])


def test_shift_end_after_start():
    assert "конец смены должен быть позже начала" in errors_for(shift_end="2026-08-17T08:00:00+03:00")


def test_shift_needs_timezone():
    assert "с часовым поясом" in errors_for(shift_start="2026-08-17T09:00:00")
