from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .models import (
    Coordinate,
    MatrixPoint,
    MatrixResponse,
    RouteLeg,
    RouteResponse,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _seconds(value: Any) -> int:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    if hasattr(value, "total_seconds"):
        return max(0, round(value.total_seconds()))
    return max(0, round(float(value)))


def _optional_string(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return str(value)


def local_departure(value: datetime) -> datetime:
    return value.astimezone(MOSCOW_TZ).replace(tzinfo=None)


def _minutes_to_seconds(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    minutes = float(value)
    if not math.isfinite(minutes) or minutes < 0:
        return None
    return round(minutes * 60)


def build_matrix_response(
    rows: list[dict[str, Any]],
    points: list[MatrixPoint],
    departure: datetime,
    settings: Settings,
) -> MatrixResponse:
    point_ids = [point.id for point in points]
    positions = {point_id: index for index, point_id in enumerate(point_ids)}
    size = len(points)
    raw: list[list[int | None]] = [[None] * size for _ in range(size)]
    for index in range(size):
        raw[index][index] = 0

    for row in rows:
        from_id = str(row.get("from_id"))
        to_id = str(row.get("to_id"))
        if from_id not in positions or to_id not in positions:
            continue
        raw[positions[from_id]][positions[to_id]] = _minutes_to_seconds(
            row.get("travel_time")
        )

    multiplier = 1 + settings.reliability_buffer_ratio
    adjusted = [
        [None if seconds is None else round(seconds * multiplier) for seconds in row]
        for row in raw
    ]
    return MatrixResponse(
        departure_time=departure,
        departure_time_window_minutes=settings.matrix_time_window_minutes,
        reliability_buffer_ratio=settings.reliability_buffer_ratio,
        point_ids=point_ids,
        raw_durations_seconds=raw,
        durations_seconds=adjusted,
    )


def build_route_response(
    rows: list[dict[str, Any]], departure: datetime, settings: Settings
) -> RouteResponse:
    if not rows:
        raise ValueError("R5 не нашёл маршрут")

    legs = []
    walking = 0
    waiting = 0
    transit = 0
    transit_routes: list[str] = []
    uses_metro = False
    for row in sorted(rows, key=lambda item: int(item.get("segment", 0))):
        mode = str(row.get("transport_mode", "UNKNOWN")).rsplit(".", 1)[-1]
        route_id = _optional_string(row.get("route_id"))
        is_transit = route_id is not None
        duration = _seconds(row.get("travel_time"))
        wait = _seconds(row.get("wait_time"))
        geometry = row.get("geometry")
        geometry_json = None
        if geometry is not None and not getattr(geometry, "is_empty", True):
            from shapely.geometry import mapping

            geometry_json = mapping(geometry)
        if mode == "WALK":
            walking += duration
        elif is_transit:
            transit += duration
            if not transit_routes or route_id != transit_routes[-1]:
                transit_routes.append(route_id)
            uses_metro |= route_id.startswith("metro-")
        waiting += wait
        distance = row.get("distance")
        legs.append(
            RouteLeg(
                mode=mode.lower(),
                duration_seconds=duration,
                wait_seconds=wait,
                distance_meters=(
                    None
                    if distance is None
                    or (isinstance(distance, float) and math.isnan(distance))
                    else round(float(distance), 1)
                ),
                route_id=route_id,
                from_stop_id=_optional_string(row.get("start_stop_id")),
                to_stop_id=_optional_string(row.get("end_stop_id")),
                geometry=geometry_json,
            )
        )

    raw = walking + transit + waiting
    entry_exit = 0
    if uses_metro:
        entry_exit = settings.metro_entry_seconds + settings.metro_exit_seconds
    buffer_seconds = round((raw + entry_exit) * settings.reliability_buffer_ratio)
    return RouteResponse(
        departure_time=departure,
        raw_duration_seconds=raw,
        entry_exit_penalty_seconds=entry_exit,
        reliability_buffer_seconds=buffer_seconds,
        total_duration_seconds=raw + entry_exit + buffer_seconds,
        walking_duration_seconds=walking,
        waiting_duration_seconds=waiting,
        transit_duration_seconds=transit,
        transfers=max(0, len(transit_routes) - 1),
        legs=legs,
    )


def route(
    network: Any,
    origin: Coordinate,
    destination: Coordinate,
    departure: datetime,
    settings: Settings,
) -> RouteResponse:
    import geopandas
    import r5py
    from shapely import Point

    origins = geopandas.GeoDataFrame(
        {"id": ["origin"], "geometry": [Point(origin.lon, origin.lat)]},
        crs="EPSG:4326",
    )
    destinations = geopandas.GeoDataFrame(
        {
            "id": ["destination"],
            "geometry": [Point(destination.lon, destination.lat)],
        },
        crs="EPSG:4326",
    )
    result = r5py.DetailedItineraries(
        network,
        origins=origins,
        destinations=destinations,
        departure=local_departure(departure),
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        speed_walking=settings.walking_speed_kmh,
        snap_to_network=True,
    )
    if result.empty:
        raise ValueError("R5 не нашёл маршрут")

    options = []
    for option, frame in result.groupby("option", sort=True):
        rows = frame.to_dict(orient="records")
        response = build_route_response(rows, departure, settings)
        options.append((response.total_duration_seconds, int(option), response))
    _, _, fastest = min(options, key=lambda item: (item[0], item[1]))
    return fastest


def travel_time_matrix(
    network: Any,
    points: list[MatrixPoint],
    departure: datetime,
    settings: Settings,
) -> MatrixResponse:
    import geopandas
    import r5py
    from shapely import Point

    locations = geopandas.GeoDataFrame(
        {
            "id": [point.id for point in points],
            "geometry": [Point(point.lon, point.lat) for point in points],
        },
        crs="EPSG:4326",
    )
    result = r5py.TravelTimeMatrix(
        network,
        origins=locations,
        destinations=locations,
        departure=local_departure(departure),
        departure_time_window=timedelta(minutes=settings.matrix_time_window_minutes),
        percentiles=[50],
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        speed_walking=settings.walking_speed_kmh,
        max_time=timedelta(minutes=settings.max_travel_minutes),
        snap_to_network=True,
    )
    return build_matrix_response(
        result.to_dict(orient="records"), points, departure, settings
    )
