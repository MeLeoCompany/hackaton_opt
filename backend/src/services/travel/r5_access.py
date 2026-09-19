"""Короткий пеший подход к связной части графа R5 для точек с карты."""

from __future__ import annotations

import csv
import io
import logging
import math
from dataclasses import replace
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx

from src.core.config import settings
from src.schemas.travel import Point, TransportKind, TravelLeg, TravelMode, TravelProvider
from src.services.travel import r5_provider, valhalla_provider

logger = logging.getLogger(__name__)

# R5 иногда привязывает точку к изолированному пешеходному ребру OSM.
# Подход ограничен несколькими минутами ходьбы, чтобы не скрыть отсутствие маршрута.
ACCESS_RADII_METERS = (100, 200)
MAX_ACCESS_DISTANCE_KM = 0.5
MAX_STOP_ACCESS_DISTANCE_KM = 1.5
MAX_NEARBY_STOPS = 3
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


@lru_cache(maxsize=2)
def _gtfs_stops(path: Path, modified_ns: int) -> tuple[Point, ...]:
    """Остановки активного GTFS: метро и наземный транспорт обрабатываются одинаково."""
    del modified_ns
    with ZipFile(path) as archive, archive.open("stops.txt") as source:
        rows = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
        return tuple(
            Point(latitude=float(row["stop_lat"]), longitude=float(row["stop_lon"]))
            for row in rows
            if row.get("location_type", "0") in {"", "0"}
            and row.get("stop_lat")
            and row.get("stop_lon")
        )


def _nearby_stops(point: Point) -> list[Point]:
    path = settings.r5_gtfs_path
    try:
        stops = _gtfs_stops(path, path.stat().st_mtime_ns)
    except (OSError, BadZipFile, KeyError, ValueError):
        logger.warning("R5: не удалось прочитать остановки GTFS из %s", path, exc_info=True)
        return []

    # Точная проверка доступности остаётся за пешеходным маршрутом Valhalla.
    cos_lat = math.cos(math.radians(point.latitude))
    nearby = []
    for stop in stops:
        north = (stop.latitude - point.latitude) * 111_320
        east = (stop.longitude - point.longitude) * 111_320 * cos_lat
        distance = math.hypot(north, east)
        if distance <= MAX_STOP_ACCESS_DISTANCE_KM * 1000:
            nearby.append((distance, stop))
    nearby.sort(key=lambda item: item[0])
    selected: list[Point] = []
    for _, stop in nearby:
        # Не тратим все попытки на платформы одной станции или соседние
        # остановки одного автобусного узла.
        if any(
            math.hypot(
                (stop.latitude - existing.latitude) * 111_320,
                (stop.longitude - existing.longitude) * 111_320 * cos_lat,
            )
            < 80
            for existing in selected
        ):
            continue
        selected.append(stop)
        if len(selected) == MAX_NEARBY_STOPS:
            break
    return selected


async def _walk(
    origin: Point, destination: Point, *, max_distance_km: float = MAX_ACCESS_DISTANCE_KM
) -> TravelLeg | None:
    try:
        legs = await valhalla_provider.route_legs([origin, destination], TransportKind.PEDESTRIAN)
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    if len(legs) != 1 or not legs[0].geometry:
        return None
    leg = legs[0]
    if leg.distance_km > max_distance_km:
        return None
    return leg.model_copy(update={"mode": TravelMode.WALK})


async def route(origin: Point, destination: Point, departure: datetime) -> r5_provider.RouteResult:
    """Сравнить R5 с прямым пешим путём и восстановить привязку при 404."""
    try:
        direct_result = await r5_provider.build_route(origin, destination, departure)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
        original_error = error
        direct_result = None

    options: list[r5_provider.RouteResult] = []
    # На коротком плече остановка может быть вовсе не нужна. Valhalla использует
    # тот же профиль пешехода, что и отдельный режим «Пешеход».
    direct_walk = await _walk(origin, destination, max_distance_km=math.inf)
    if direct_walk is not None:
        options.append(
            r5_provider.RouteResult(
                legs=[direct_walk],
                total_duration_min=direct_walk.duration_min,
                walking_duration_min=direct_walk.duration_min,
                waiting_duration_min=0,
                transit_duration_min=0,
                entry_exit_penalty_min=0,
                reliability_buffer_min=0,
                transfers=0,
                provider=TravelProvider.VALHALLA,
            )
        )
    if direct_result is not None:
        options.append(direct_result)
        return min(options, key=lambda option: option.total_duration_min)
    stop_access: dict[bool, list[tuple[Point, TravelLeg]]] = {True: [], False: []}
    for is_origin, point in ((True, origin), (False, destination)):
        stop_candidates = _nearby_stops(point)
        candidates = [*stop_candidates, *_nearby_points(point)]
        for candidate in candidates:
            access_limit = (
                MAX_STOP_ACCESS_DISTANCE_KM
                if candidate in stop_candidates
                else MAX_ACCESS_DISTANCE_KM
            )
            walk = await _walk(
                point if is_origin else candidate,
                candidate if is_origin else point,
                max_distance_km=access_limit,
            )
            if walk is None:
                continue
            if candidate in stop_candidates:
                stop_access[is_origin].append((candidate, walk))
            try:
                result = await r5_provider.build_route(
                    candidate if is_origin else origin,
                    destination if is_origin else candidate,
                    departure + timedelta(minutes=walk.duration_min) if is_origin else departure,
                )
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    continue
                raise
            options.append(
                replace(
                    result,
                    legs=[walk, *result.legs] if is_origin else [*result.legs, walk],
                    total_duration_min=result.total_duration_min + walk.duration_min,
                    walking_duration_min=result.walking_duration_min + walk.duration_min,
                )
            )

    # Обе исходные точки могут оказаться на изолированных рёбрах. В этом случае
    # проверяем ограниченное число пар остановок, не перебирая все смещения.
    if not any(option.provider is TravelProvider.R5 for option in options):
        for start, start_walk in stop_access[True]:
            for end, end_walk in stop_access[False]:
                try:
                    result = await r5_provider.build_route(
                        start,
                        end,
                        departure + timedelta(minutes=start_walk.duration_min),
                    )
                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 404:
                        continue
                    raise
                options.append(
                    replace(
                        result,
                        legs=[start_walk, *result.legs, end_walk],
                        total_duration_min=(
                            result.total_duration_min
                            + start_walk.duration_min
                            + end_walk.duration_min
                        ),
                        walking_duration_min=(
                            result.walking_duration_min
                            + start_walk.duration_min
                            + end_walk.duration_min
                        ),
                    )
                )

    if options:
        logger.info("R5: найден пеший подход к остановке или связной части графа")
        return min(options, key=lambda option: option.total_duration_min)

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
