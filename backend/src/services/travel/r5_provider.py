"""Матрица и подробные маршруты общественного транспорта из локального R5."""

from __future__ import annotations

import csv
import io
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx

from src.core.config import settings
from src.schemas.travel import Point, TravelLeg, TravelMode, TravelProvider
from src.services.travel.polyline import encode

logger = logging.getLogger(__name__)
HEX_COLOR = re.compile(r"[0-9A-Fa-f]{6}\Z")


@lru_cache(maxsize=2)
def _route_colors(path: Path, modified_ns: int) -> dict[str, str]:
    del modified_ns
    with ZipFile(path) as archive, archive.open("routes.txt") as source:
        rows = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
        return {
            row["route_id"]: f"#{color.upper()}"
            for row in rows
            if (color := (row.get("route_color") or "").lstrip("#")) and HEX_COLOR.fullmatch(color)
        }


def _color_for_route(route_id: str | None) -> str | None:
    if route_id is None:
        return None
    path = settings.r5_gtfs_path
    try:
        return _route_colors(path, path.stat().st_mtime_ns).get(route_id)
    except (OSError, BadZipFile, KeyError, ValueError):
        logger.warning("R5: не удалось прочитать цвета маршрутов из %s", path, exc_info=True)
        return None


@lru_cache(maxsize=2)
def _route_names(path: Path, modified_ns: int) -> dict[str, str]:
    del modified_ns
    with ZipFile(path) as archive, archive.open("routes.txt") as source:
        rows = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
        return {
            row["route_id"]: name
            for row in rows
            if (name := (row.get("route_short_name") or "").strip())
        }


def _name_for_route(route_id: str | None) -> str | None:
    if route_id is None:
        return None
    path = settings.r5_gtfs_path
    try:
        return _route_names(path, path.stat().st_mtime_ns).get(route_id)
    except (OSError, BadZipFile, KeyError, ValueError):
        logger.warning("R5: не удалось прочитать названия маршрутов из %s", path, exc_info=True)
        return None


@dataclass(frozen=True)
class RouteResult:
    legs: list[TravelLeg]
    total_duration_min: float
    walking_duration_min: float
    waiting_duration_min: float
    transit_duration_min: float
    entry_exit_penalty_min: float
    reliability_buffer_min: float
    transfers: int
    provider: TravelProvider = TravelProvider.R5


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


def _number(value: object, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"R5 вернул некорректное поле {field}")  # noqa: TRY004
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"R5 вернул некорректное поле {field}")
    return result


def _mode(value: object, route_id: str | None) -> TravelMode:
    name = str(value).lower()
    if name == "walk":
        return TravelMode.WALK
    if name in {"subway", "metro"} or (route_id or "").startswith("metro-"):
        return TravelMode.METRO
    return {
        "bus": TravelMode.BUS,
        "tram": TravelMode.TRAM,
        "rail": TravelMode.RAIL,
        "ferry": TravelMode.FERRY,
    }.get(name, TravelMode.TRANSIT)


def _geometry(value: object) -> tuple[str, float]:
    if value is None:
        return "", 0
    if not isinstance(value, dict):
        raise ValueError("R5 вернул геометрию неизвестного формата")  # noqa: TRY004
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "MultiLineString" and isinstance(coordinates, list):
        coordinates = [coordinate for line in coordinates for coordinate in line]
    if geometry_type not in {"LineString", "MultiLineString"} or not isinstance(coordinates, list):
        raise ValueError("R5 вернул геометрию неизвестного формата")
    points = []
    for coordinate in coordinates:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) < 2
            or isinstance(coordinate[0], bool)
            or isinstance(coordinate[1], bool)
            or not isinstance(coordinate[0], (int, float))
            or not isinstance(coordinate[1], (int, float))
        ):
            raise ValueError("R5 вернул некорректные координаты геометрии")
        points.append(Point(longitude=float(coordinate[0]), latitude=float(coordinate[1])))
    if len(points) < 2:
        return "", 0
    distance_km = 0.0
    for origin, destination in pairwise(points):
        latitude_delta = math.radians(destination.latitude - origin.latitude)
        longitude_delta = math.radians(destination.longitude - origin.longitude)
        origin_latitude = math.radians(origin.latitude)
        destination_latitude = math.radians(destination.latitude)
        haversine = math.sin(latitude_delta / 2) ** 2 + (
            math.cos(origin_latitude)
            * math.cos(destination_latitude)
            * math.sin(longitude_delta / 2) ** 2
        )
        distance_km += 6371.0088 * 2 * math.asin(min(1, math.sqrt(haversine)))
    return encode(points), distance_km


def _parse_route(payload: object) -> RouteResult:
    if not isinstance(payload, dict):
        raise ValueError("R5 вернул ответ неизвестного формата")  # noqa: TRY004
    raw_legs = payload.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("R5 вернул маршрут без участков")
    legs = []
    for raw_leg in raw_legs:
        if not isinstance(raw_leg, dict):
            raise ValueError("R5 вернул участок неизвестного формата")  # noqa: TRY004
        route_id_value = raw_leg.get("route_id")
        route_id = None if route_id_value is None else str(route_id_value)
        duration = _number(raw_leg.get("duration_seconds"), "duration_seconds")
        wait = _number(raw_leg.get("wait_seconds"), "wait_seconds")
        distance = _number(raw_leg.get("distance_meters"), "distance_meters", nullable=True)
        geometry, geometry_distance_km = _geometry(raw_leg.get("geometry"))
        assert duration is not None and wait is not None
        legs.append(
            TravelLeg(
                distance_km=round(
                    distance / 1000 if distance is not None else geometry_distance_km, 3
                ),
                duration_min=round((duration + wait) / 60, 1),
                wait_min=round(wait / 60, 1),
                geometry=geometry,
                mode=_mode(raw_leg.get("mode"), route_id),
                route_id=route_id,
                route_short_name=_name_for_route(route_id),
                route_color=_color_for_route(route_id),
                from_stop_id=(
                    None if raw_leg.get("from_stop_id") is None else str(raw_leg["from_stop_id"])
                ),
                to_stop_id=(
                    None if raw_leg.get("to_stop_id") is None else str(raw_leg["to_stop_id"])
                ),
            )
        )

    def minutes(field: str) -> float:
        value = _number(payload.get(field), field)
        assert value is not None
        return value / 60

    transfers = payload.get("transfers")
    if isinstance(transfers, bool) or not isinstance(transfers, int) or transfers < 0:
        raise ValueError("R5 вернул некорректное число пересадок")
    return RouteResult(
        legs=legs,
        total_duration_min=minutes("total_duration_seconds"),
        walking_duration_min=minutes("walking_duration_seconds"),
        waiting_duration_min=minutes("waiting_duration_seconds"),
        transit_duration_min=minutes("transit_duration_seconds"),
        entry_exit_penalty_min=minutes("entry_exit_penalty_seconds"),
        reliability_buffer_min=minutes("reliability_buffer_seconds"),
        transfers=transfers,
    )


async def build_route(origin: Point, destination: Point, departure_time: datetime) -> RouteResult:
    """Один составной маршрут R5: пешие и транспортные участки с геометрией."""
    if departure_time.tzinfo is None:
        raise ValueError("для маршрута R5 требуется время с часовым поясом")
    request = {
        "origin": {"lat": origin.latitude, "lon": origin.longitude},
        "destination": {"lat": destination.latitude, "lon": destination.longitude},
        "departure_time": departure_time.isoformat(),
    }
    async with httpx.AsyncClient(
        base_url=settings.r5_url, timeout=settings.r5_timeout_seconds
    ) as client:
        response = await client.post("/route", json=request)
        response.raise_for_status()
    return _parse_route(response.json())
