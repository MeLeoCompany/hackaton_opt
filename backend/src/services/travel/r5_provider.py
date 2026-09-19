"""Матрица времени общественного транспорта из локального сервиса R5."""

from __future__ import annotations

import math
from datetime import datetime

import httpx

from src.core.config import settings
from src.schemas.travel import Point


def _point_id(index: int) -> str:
    return f"point-{index}"


def _parse_durations(payload: object, point_count: int) -> list[list[float | None]]:
    if not isinstance(payload, dict):
        raise ValueError("R5 вернул ответ неизвестного формата")  # noqa: TRY004

    expected_ids = [_point_id(index) for index in range(point_count)]
    if payload.get("point_ids") != expected_ids:
        raise ValueError("R5 изменил порядок или идентификаторы точек матрицы")

    values = payload.get("durations_seconds")
    if not isinstance(values, list) or len(values) != point_count:
        raise ValueError("R5 вернул матрицу неправильного размера")

    durations: list[list[float | None]] = []
    for row in values:
        if not isinstance(row, list) or len(row) != point_count:
            raise ValueError("R5 вернул матрицу неправильного размера")
        parsed_row: list[float | None] = []
        for seconds in row:
            if seconds is None:
                parsed_row.append(None)
                continue
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
                raise ValueError("R5 вернул некорректное время поездки")  # noqa: TRY004
            seconds = float(seconds)
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError("R5 вернул некорректное время поездки")
            parsed_row.append(seconds / 60)
        durations.append(parsed_row)
    return durations


async def build_duration_matrix(
    points: list[Point], departure_time: datetime
) -> list[list[float | None]]:
    """Время между всеми точками в минутах, включая запас надёжности R5."""
    if departure_time.tzinfo is None:
        raise ValueError("для матрицы R5 требуется время с часовым поясом")

    request = {
        "points": [
            {
                "id": _point_id(index),
                "lat": point.latitude,
                "lon": point.longitude,
            }
            for index, point in enumerate(points)
        ],
        "departure_time": departure_time.isoformat(),
    }
    async with httpx.AsyncClient(
        base_url=settings.r5_url, timeout=settings.r5_timeout_seconds
    ) as client:
        response = await client.post("/matrix", json=request)
        response.raise_for_status()
    return _parse_durations(response.json(), len(points))
