from __future__ import annotations

import csv
import io
import math
import zipfile
from collections.abc import Iterable
from datetime import date, datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

from .common import gtfs_time, read_json
from .metro_transfers import cluster_metro_stations, transfer_rows

AGENCY_ID = "moscow-transport-pilot"


def _csv_bytes(header: list[str], rows: Iterable[Iterable[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _minutes(value: str) -> int:
    hours, minute, seconds = (int(part) for part in value.split(":"))
    if seconds:
        raise ValueError("доли минуты во времени GTFS не поддерживаются")
    return hours * 60 + minute


def _date(value: str) -> str:
    return date.fromisoformat(value).strftime("%Y%m%d")


def _distributed_offsets(stops: list[dict[str, Any]], duration: int) -> list[int]:
    distances = [0.0]
    for left, right in pairwise(stops):
        lat_scale = math.cos(math.radians((left["lat"] + right["lat"]) / 2))
        dx = (right["lon"] - left["lon"]) * lat_scale
        dy = right["lat"] - left["lat"]
        distances.append(distances[-1] + math.hypot(dx, dy))
    if not distances[-1]:
        return [0 for _ in stops]
    return [round(duration * value / distances[-1]) for value in distances]


def build_gtfs(inputs: list[Path], output: Path) -> None:
    datasets = [read_json(path) for path in inputs]
    metro_clusters = cluster_metro_stations(datasets)
    parent_by_stop = {
        stop_id: cluster.station_id
        for cluster in metro_clusters
        for stop_id in cluster.stop_ids
    }
    service_starts = [
        dataset["source"]["service_date"]
        if dataset["kind"] == "bus_exact"
        else dataset["service"]["start_date"]
        for dataset in datasets
    ]
    service_ends = [
        dataset["source"]["service_date"]
        if dataset["kind"] == "bus_exact"
        else dataset["service"]["end_date"]
        for dataset in datasets
    ]
    tables: dict[str, list[list[Any]]] = {
        "stops.txt": [],
        "routes.txt": [],
        "trips.txt": [],
        "stop_times.txt": [],
        "calendar.txt": [],
        "calendar_dates.txt": [],
        "frequencies.txt": [],
        "shapes.txt": [],
        "feed_info.txt": [],
        "attributions.txt": [],
        "transfers.txt": transfer_rows(metro_clusters),
    }
    stop_seen: set[str] = set()
    route_seen: set[str] = set()
    shape_seen: set[str] = set()

    for cluster in metro_clusters:
        tables["stops.txt"].append(
            [cluster.station_id, cluster.name, cluster.lat, cluster.lon, 1, ""]
        )
        stop_seen.add(cluster.station_id)

    for dataset in datasets:
        route = dataset["route"]
        route_id = route["source_route_id"]
        if route_id not in route_seen:
            tables["routes.txt"].append(
                [
                    route_id,
                    AGENCY_ID,
                    route["short_name"],
                    route.get("long_name", ""),
                    route["route_type"],
                    route.get("color", ""),
                ]
            )
            route_seen.add(route_id)
        if dataset["kind"] == "bus_exact":
            service_id = f"bus-{route_id}-{dataset['source']['service_date']}"
            tables["calendar_dates.txt"].append(
                [service_id, _date(dataset["source"]["service_date"]), 1]
            )
            for pattern in dataset["patterns"]:
                shape_id = f"{route_id}-{pattern['direction_id']}"
                if shape_id not in shape_seen:
                    for sequence, (lon, lat) in enumerate(pattern["shape"], start=1):
                        tables["shapes.txt"].append([shape_id, lat, lon, sequence])
                    shape_seen.add(shape_id)
                for stop in pattern["stops"]:
                    stop_id = f"bus-{stop['source_stop_id']}"
                    if stop_id not in stop_seen:
                        tables["stops.txt"].append(
                            [stop_id, stop["name"], stop["lat"], stop["lon"], 0, ""]
                        )
                        stop_seen.add(stop_id)
                for trip_index in range(len(pattern["stops"][0]["departures"])):
                    service_date = dataset["source"]["service_date"]
                    trip_id = f"{shape_id}-{service_date}-{trip_index + 1}"
                    tables["trips.txt"].append(
                        [
                            route_id,
                            service_id,
                            trip_id,
                            pattern["direction_id"],
                            shape_id,
                        ]
                    )
                    for sequence, stop in enumerate(pattern["stops"], start=1):
                        value = gtfs_time(stop["departures"][trip_index])
                        tables["stop_times.txt"].append(
                            [
                                trip_id,
                                value,
                                value,
                                f"bus-{stop['source_stop_id']}",
                                sequence,
                            ]
                        )
        elif dataset["kind"] == "metro_frequency":
            service_id = f"metro-{route_id}-daily"
            service = dataset["service"]
            tables["calendar.txt"].append(
                [
                    service_id,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    _date(service["start_date"]),
                    _date(service["end_date"]),
                ]
            )
            for pattern in dataset["patterns"]:
                pattern_id = pattern.get("pattern_id", pattern["direction_id"])
                trip_id = f"{route_id}-{pattern_id}-frequency"
                tables["trips.txt"].append(
                    [route_id, service_id, trip_id, pattern["direction_id"], ""]
                )
                offsets = _distributed_offsets(
                    pattern["stops"], pattern["duration_minutes"]
                )
                start = _minutes(service["headways"][0]["start"])
                for sequence, (stop, offset) in enumerate(
                    zip(pattern["stops"], offsets, strict=True), start=1
                ):
                    stop_id = stop["source_stop_id"]
                    if stop_id not in stop_seen:
                        tables["stops.txt"].append(
                            [
                                stop_id,
                                stop["name"],
                                stop["lat"],
                                stop["lon"],
                                0,
                                parent_by_stop[stop_id],
                            ]
                        )
                        stop_seen.add(stop_id)
                    value = gtfs_time(start + offset)
                    tables["stop_times.txt"].append(
                        [trip_id, value, value, stop_id, sequence]
                    )
                for headway in service["headways"]:
                    tables["frequencies.txt"].append(
                        [
                            trip_id,
                            headway["start"],
                            headway["end"],
                            headway["seconds"],
                            0,
                        ]
                    )
        else:
            raise ValueError(f"неподдерживаемый вид набора данных: {dataset['kind']}")

    headers = {
        "stops.txt": [
            "stop_id",
            "stop_name",
            "stop_lat",
            "stop_lon",
            "location_type",
            "parent_station",
        ],
        "routes.txt": [
            "route_id",
            "agency_id",
            "route_short_name",
            "route_long_name",
            "route_type",
            "route_color",
        ],
        "trips.txt": ["route_id", "service_id", "trip_id", "direction_id", "shape_id"],
        "stop_times.txt": [
            "trip_id",
            "arrival_time",
            "departure_time",
            "stop_id",
            "stop_sequence",
        ],
        "calendar.txt": [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        "calendar_dates.txt": ["service_id", "date", "exception_type"],
        "frequencies.txt": [
            "trip_id",
            "start_time",
            "end_time",
            "headway_secs",
            "exact_times",
        ],
        "shapes.txt": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
        "feed_info.txt": [
            "feed_publisher_name",
            "feed_publisher_url",
            "feed_lang",
            "feed_start_date",
            "feed_end_date",
            "feed_version",
            "feed_contact_url",
        ],
        "attributions.txt": [
            "attribution_id",
            "organization_name",
            "is_producer",
            "is_operator",
            "is_authority",
            "attribution_url",
        ],
        "transfers.txt": [
            "from_stop_id",
            "to_stop_id",
            "transfer_type",
            "min_transfer_time",
        ],
    }
    tables["feed_info.txt"].append(
        [
            "Пилотный набор Московского транспорта hackaton_opt",
            "https://transport.mos.ru/",
            "ru",
            _date(min(service_starts)),
            _date(max(service_ends)),
            datetime.now(timezone.utc).date().isoformat(),
            "https://github.com/MeLeoCompany/hackaton_opt",
        ]
    )
    tables["attributions.txt"].extend(
        [
            [
                "moscow-transport",
                "Единый транспортный портал Москвы",
                1,
                0,
                1,
                "https://transport.mos.ru/",
            ],
            [
                "openstreetmap",
                "OpenStreetMap contributors",
                1,
                0,
                0,
                "https://www.openstreetmap.org/copyright",
            ],
        ]
    )
    agency = _csv_bytes(
        ["agency_id", "agency_name", "agency_url", "agency_timezone", "agency_lang"],
        [
            [
                AGENCY_ID,
                "Московский транспорт (пилот)",
                "https://transport.mos.ru/",
                "Europe/Moscow",
                "ru",
            ]
        ],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agency.txt", agency)
        for name, rows in tables.items():
            if rows:
                archive.writestr(name, _csv_bytes(headers[name], rows))
