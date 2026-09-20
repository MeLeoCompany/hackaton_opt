"""Системное время сервера — одно на всё приложение.

Для демонстрации время можно перемотать вперёд: тогда «сейчас» у пересчёта плана, отметок
бригад и расчёта опозданий сдвигается, и не нужно ждать реального наступления времени.
Сдвиг хранится в таблице `system_time` (миграция 034) и читается при старте приложения;
здесь он лежит в памяти, потому что now() вызывается из синхронного кода.
"""

from datetime import UTC, datetime, timedelta

_offset = timedelta(0)


def now() -> datetime:
    """Текущее системное время с учётом сдвига демонстрации."""
    return datetime.now(UTC) + _offset


def real_now() -> datetime:
    """Настоящее время без сдвига — чтобы показать, насколько перемотали."""
    return datetime.now(UTC)


def offset() -> timedelta:
    return _offset


def set_offset(value: timedelta) -> None:
    global _offset
    _offset = value
