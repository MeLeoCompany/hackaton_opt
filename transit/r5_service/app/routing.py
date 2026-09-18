from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .models import Coordinate, RouteLeg, RouteResponse

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


def build_route_response(
    rows: list[dict[str, Any]], departure: datetime, settings: Settings
) -> RouteResponse:
    if not rows:
        raise ValueError("R5 не нашёл маршрут")

    legs = []
    walking = 0
    waiting = 0
    transit = 0
    transit_legs = 0
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
            transit_legs += 1
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
        transfers=max(0, transit_legs - 1),
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
