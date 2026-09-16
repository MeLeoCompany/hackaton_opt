"""Местный (московский) день: из даты в границы суток.

День — ключевой параметр сервиса: и заявки, и смены исполнителей, и план выбираются на день.
Время в БД хранится в UTC, поэтому границы дня считаются с местным смещением из настроек.
"""

from datetime import date, datetime, time, timedelta, timezone

from src.core.config import settings


def local_timezone() -> timezone:
    return timezone(timedelta(hours=settings.local_utc_offset_hours))


def day_bounds(plan_date: date) -> tuple[datetime, datetime]:
    """Дата -> (00:00 этого дня, 00:00 следующего) по местному времени."""
    day_start = datetime.combine(plan_date, time.min, tzinfo=local_timezone())
    return day_start, day_start + timedelta(days=1)


def intersected_local_dates(period_start: datetime, period_end: datetime) -> list[date]:
    """Местные даты, с которыми пересекается полуинтервал [start, end).

    Конец ровно в 00:00 следующего дня не добавляет этот день: в нём у периода
    нет ни одной секунды. Это та же семантика, что у выборок из БД.
    """
    if period_end <= period_start:
        return []

    timezone_ = local_timezone()
    first = period_start.astimezone(timezone_).date()
    last = (period_end.astimezone(timezone_) - timedelta(microseconds=1)).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
