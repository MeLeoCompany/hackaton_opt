"""Проверки полей заявки — без БД."""

import pytest
from pydantic import ValidationError

from src.schemas.requests import RequestCreate

VALID = {
    "address": "Москва, ул. Тестовая, 1",
    "latitude": 55.75,
    "longitude": 37.62,
    "duration_minutes": 30,
    "window_start": "2026-08-17T10:00:00+03:00",
    "window_end": "2026-08-17T12:00:00+03:00",
    "priority_id": 1,
    "skill_id": 1,
}


def test_address_is_trimmed_and_cannot_be_only_spaces():
    assert RequestCreate(**{**VALID, "address": "  Москва  "}).address == "Москва"
    with pytest.raises(ValidationError) as caught:
        RequestCreate(**{**VALID, "address": "   "})
    assert "address" in str(caught.value)
