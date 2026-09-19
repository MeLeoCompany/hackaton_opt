"""Короткий пеший подход к связной части графа R5 для точек с карты."""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from datetime import datetime, timedelta

import httpx

from src.schemas.travel import Point, TransportKind, TravelLeg, TravelMode
from src.services.travel import r5_provider, valhalla_provider

logger = logging.getLogger(__name__)

# R5 иногда привязывает точку к изолированному пешеходному ребру OSM.
# Подход ограничен несколькими минутами ходьбы, чтобы не скрыть отсутствие маршрута.
ACCESS_RADII_METERS = (100, 200)
MAX_ACCESS_DISTANCE_KM = 0.5
MAX_MATRIX_REPAIR_POINTS = 8


def _nearby_points(point: Point):
    latitude_step = 1 / 111_320
    longitude_step = latitude_step / math.cos(math.radians(point.latitude))
    for radius in ACCESS_RADII_METERS:
        for north, east in ((-1, 0), (1, 0), (0, 1), (0, -1)):
            yield Point(
                latitude=point.latitude + north * radius * latitude_step,
                longitude=point.longitude + east * radius * longitude_step,
            )


async def _walk(origin: Point, destination: Point) -> TravelLeg | None:
    try:
        legs = await valhalla_provider.route_legs(
            [origin, destination], TransportKind.PEDESTRIAN
        )
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    if len(legs) != 1 or not legs[0].geometry:
        return None
    leg = legs[0]
    if leg.distance_km > MAX_ACCESS_DISTANCE_KM:
        return None
    return leg.model_copy(update={"mode": TravelMode.WALK})


async def route(
    origin: Point, destination: Point, departure: datetime
) -> r5_provider.RouteResult:
    """Повторить поиск только при 404 R5, добавив проверенный пеший участок."""
    try:
        return await r5_provider.build_route(origin, destination, departure)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
        original_error = error

    for candidate in _nearby_points(origin):
        walk = await _walk(origin, candidate)
        if walk is None:
            continue
        try:
            result = await r5_provider.build_route(
                candidate, destination, departure + timedelta(minutes=walk.duration_min)
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                continue
            raise
        logger.info("R5: найден пеший подход к начальной точке графа")
        return replace(
            result,
            legs=[walk, *result.legs],
            total_duration_min=result.total_duration_min + walk.duration_min,
            walking_duration_min=result.walking_duration_min + walk.duration_min,
        )

    for candidate in _nearby_points(destination):
        walk = await _walk(candidate, destination)
        if walk is None:
            continue
        try:
            result = await r5_provider.build_route(origin, candidate, departure)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                continue
            raise
        logger.info("R5: найден пеший подход от конечной точки графа")
        return replace(
            result,
            legs=[*result.legs, walk],
            total_duration_min=result.total_duration_min + walk.duration_min,
            walking_duration_min=result.walking_duration_min + walk.duration_min,
        )

    raise original_error


async def repair_duration_matrix(
    points: list[Point],
    departure: datetime,
    durations: list[list[float | None]],
) -> list[list[float | None]]:
    """Восстановить строки и столбцы точек, изолированных при привязке R5.

    Один запрос матрицы для соседней точки восстанавливает сразу все доступные
    направления. Обычные и действительно недоступные пары остаются без изменений.
    """
    repaired = [row.copy() for row in durations]
    attempted = 0
    for index, point in enumerate(points):
        if any(
            repaired[index][other] is not None or repaired[other][index] is not None
            for other in range(len(points))
            if other != index
        ):
            continue
        if attempted >= MAX_MATRIX_REPAIR_POINTS:
            logger.warning("R5: достигнут предел проверки изолированных точек матрицы")
            break
        attempted += 1

        for candidate in _nearby_points(point):
            outward = await _walk(point, candidate)
            inward = await _walk(candidate, point)
            if outward is None and inward is None:
                continue
            try:
                candidate_points = points.copy()
                candidate_points[index] = candidate
                candidate_matrix = await r5_provider.build_duration_matrix(
                    candidate_points, departure
                )
            except (httpx.HTTPError, KeyError, ValueError):
                logger.warning("R5: не удалось проверить соседнюю точку матрицы", exc_info=True)
                break

            restored = False
            for other in range(len(points)):
                if other == index:
                    continue
                if outward is not None and repaired[index][other] is None:
                    duration = candidate_matrix[index][other]
                    if duration is not None:
                        repaired[index][other] = duration + outward.duration_min
                        restored = True
                if inward is not None and repaired[other][index] is None:
                    duration = candidate_matrix[other][index]
                    if duration is not None:
                        repaired[other][index] = duration + inward.duration_min
                        restored = True
            if restored:
                logger.info("R5: восстановлены направления матрицы через пеший подход")
                break
    return repaired
