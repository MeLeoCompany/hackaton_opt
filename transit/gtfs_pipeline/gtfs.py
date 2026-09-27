from __future__ import annotations

import csv
import io
import math
import os
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

from .common import gtfs_time, read_json
from .metro_transfers import cluster_metro_stations, transfer_rows
from .validate import validate_gtfs

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


def _metro_service_start(service: dict[str, Any]) -> str:
    """Начало года данных: расчётное метро действует ежедневно, а не со дня сбора."""
    collected = date.fromisoformat(service["start_date"])
    return collected.replace(month=1, day=1).isoformat()


def _load_datasets(inputs: list[Path]) -> list[dict[str, Any]]:
    datasets = []
    for path in inputs:
        dataset = read_json(path)
        if dataset["kind"] not in {"bus_weekly", "scheduled_service"}:
            datasets.append(dataset)
            continue
        if dataset["kind"] == "scheduled_service":
            service = dataset["service"]
            start = date.fromisoformat(service["start_date"])
            end = date.fromisoformat(service["end_date"])
            weekdays = service["weekdays"]
            if (
                start > end
                or not weekdays
                or len(set(weekdays)) != len(weekdays)
                or any(
                    not isinstance(day, int)
                    or isinstance(day, bool)
                    or not 0 <= day <= 6
                    for day in weekdays
                )
            ):
                raise ValueError(f"некорректный календарь транспорта: {path}")
            for pattern in dataset["patterns"]:
                stop_count = len(pattern["stops"])
                if stop_count < 2 or any(
                    len(trip) != stop_count for trip in pattern["trips"]
                ):
                    raise ValueError(f"некорректные рейсы транспорта: {path}")
                if any(
                    any(right < left for left, right in pairwise(trip))
                    for trip in pattern["trips"]
                ):
                    raise ValueError(f"время рейса идёт назад: {path}")
            datasets.append(dataset)
            continue
        service = dataset["service"]
        start = date.fromisoformat(service["start_date"])
        end = date.fromisoformat(service["end_date"])
        weekdays = service["weekdays"]
        if (
            start > end
            or not weekdays
            or len(set(weekdays)) != len(weekdays)
            or any(
                not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6
                for day in weekdays
            )
        ):
            raise ValueError(f"некорректный календарь автобуса: {path}")
        template = read_json(path.parent / dataset["template"])
        if template["kind"] != "bus_exact":
            raise ValueError(f"шаблон автобуса должен быть точным днём: {path}")
        template_date = date.fromisoformat(template["source"]["service_date"])
        if start < template_date and dataset["source"].get("retrospective") is not True:
            raise ValueError(
                f"ретроспективное расписание автобуса должно быть явно помечено: {path}"
            )
        for example in dataset.get("matching_examples", []):
            observed = read_json(path.parent / example)
            if (
                observed["kind"] != "bus_exact"
                or observed["route"] != template["route"]
                or observed["patterns"] != template["patterns"]
            ):
                raise ValueError(f"контрольная дата отличается от шаблона: {example}")
        datasets.append(
            {
                "kind": "bus_weekly",
                "route": template["route"],
                "patterns": template["patterns"],
                "service": service,
                "source": dataset["source"],
            }
        )
    weekly = [dataset for dataset in datasets if dataset["kind"] == "bus_weekly"]
    for index, left in enumerate(weekly):
        for right in weekly[index + 1 :]:
            if (
                left["route"]["source_route_id"] == right["route"]["source_route_id"]
                and set(left["service"]["weekdays"]) & set(right["service"]["weekdays"])
                and left["service"]["start_date"] <= right["service"]["end_date"]
                and right["service"]["start_date"] <= left["service"]["end_date"]
            ):
                raise ValueError("пересекаются недельные календари одного автобуса")

    # Для пилотных автобусов один будний снимок намеренно действует каждый день.
    # Точные выходные снимки храним как исходные данные, но не добавляем в GTFS:
    # иначе отдельный service_id снова включит выходное расписание поверх шаблона.
    weekday_daily = {
        dataset["route"]["source_route_id"]: dataset["source"]["template_date"]
        for dataset in weekly
        if dataset["source"].get("calendar_policy") == "weekday_daily"
    }
    return [
        dataset
        for dataset in datasets
        if dataset["kind"] != "bus_exact"
        or dataset["route"]["source_route_id"] not in weekday_daily
        or dataset["source"]["service_date"]
        == weekday_daily[dataset["route"]["source_route_id"]]
    ]


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
    datasets = _load_datasets(inputs)
    metro_clusters = cluster_metro_stations(datasets)
    parent_by_stop = {
        stop_id: cluster.station_id
        for cluster in metro_clusters
        for stop_id in cluster.stop_ids
    }
    service_starts = []
    service_ends = []
    for dataset in datasets:
        if dataset["kind"] == "bus_exact":
            start = end = dataset["source"]["service_date"]
        elif dataset["kind"] == "bus_weekly":
            start, end = (
                dataset["service"]["start_date"],
                dataset["service"]["end_date"],
            )
        elif dataset["kind"] == "metro_frequency":
            start, end = (
                _metro_service_start(dataset["service"]),
                dataset["service"]["end_date"],
            )
        else:
            start, end = (
                dataset["service"]["start_date"],
                dataset["service"]["end_date"],
            )
        service_starts.append(start)
        service_ends.append(end)
    exact_dates: dict[str, set[str]] = {}
    for dataset in datasets:
        if dataset["kind"] == "bus_exact":
            exact_dates.setdefault(dataset["route"]["source_route_id"], set()).add(
                dataset["source"]["service_date"]
            )
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
        if dataset["kind"] in {"bus_exact", "bus_weekly"}:
            night_service = dataset["source"].get("night_service", False)
            if dataset["kind"] == "bus_exact":
                service_id = f"bus-{route_id}-{dataset['source']['service_date']}"
                tables["calendar_dates.txt"].append(
                    [service_id, _date(dataset["source"]["service_date"]), 1]
                )
                if night_service:
                    following = date.fromisoformat(
                        dataset["source"]["service_date"]
                    ) + timedelta(days=1)
                    tables["calendar_dates.txt"].append(
                        [f"{service_id}-morning", following.strftime("%Y%m%d"), 1]
                    )
            else:
                service = dataset["service"]
                service_id = f"bus-{route_id}-weekly-{service['start_date']}-{'-'.join(map(str, service['weekdays']))}"
                tables["calendar.txt"].append(
                    [
                        service_id,
                        *(int(day in service["weekdays"]) for day in range(7)),
                        _date(service["start_date"]),
                        _date(service["end_date"]),
                    ]
                )
                if night_service:
                    tables["calendar.txt"].append(
                        [
                            f"{service_id}-morning",
                            *(
                                int((day - 1) % 7 in service["weekdays"])
                                for day in range(7)
                            ),
                            _date(
                                (
                                    date.fromisoformat(service["start_date"])
                                    + timedelta(days=1)
                                ).isoformat()
                            ),
                            _date(
                                (
                                    date.fromisoformat(service["end_date"])
                                    + timedelta(days=1)
                                ).isoformat()
                            ),
                        ]
                    )
                for exact_day in exact_dates.get(route_id, set()):
                    parsed = date.fromisoformat(exact_day)
                    if (
                        service["start_date"] <= exact_day <= service["end_date"]
                        and parsed.weekday() in service["weekdays"]
                    ):
                        tables["calendar_dates.txt"].append(
                            [service_id, _date(exact_day), 2]
                        )
                        if night_service:
                            following = date.fromisoformat(exact_day) + timedelta(
                                days=1
                            )
                            tables["calendar_dates.txt"].append(
                                [
                                    f"{service_id}-morning",
                                    following.strftime("%Y%m%d"),
                                    2,
                                ]
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
                    trip_id = f"{shape_id}-{service_id}-{trip_index + 1}"
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
                    if night_service:
                        morning_stops = [
                            stop
                            for stop in pattern["stops"]
                            if stop["departures"][trip_index] >= 24 * 60
                        ]
                        if len(morning_stops) >= 2:
                            morning_trip = f"{trip_id}-morning"
                            tables["trips.txt"].append(
                                [
                                    route_id,
                                    f"{service_id}-morning",
                                    morning_trip,
                                    pattern["direction_id"],
                                    "",
                                ]
                            )
                            for sequence, stop in enumerate(morning_stops, start=1):
                                value = gtfs_time(
                                    stop["departures"][trip_index] - 24 * 60
                                )
                                tables["stop_times.txt"].append(
                                    [
                                        morning_trip,
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
                    _date(_metro_service_start(service)),
                    _date(service["end_date"]),
                ]
            )
            for pattern in dataset["patterns"]:
                pattern_id = pattern.get("pattern_id", pattern["direction_id"])
                offsets = _distributed_offsets(
                    pattern["stops"], pattern["duration_minutes"]
                )
                for stop in pattern["stops"]:
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

                # Матричный движок R5 понимает вероятностные частотные рейсы, но
                # движок подробных маршрутов не всегда восстанавливает их участки.
                # Разворачиваем расчётные интервалы в конкретные отправления, чтобы
                # оба режима использовали одно расписание.
                for headway in service["headways"]:
                    first = _minutes(headway["start"])
                    end = _minutes(headway["end"])
                    if headway["seconds"] % 60:
                        raise ValueError(
                            "интервал метро должен задаваться целым числом минут"
                        )
                    step = headway["seconds"] // 60
                    for departure in range(first, end, step):
                        trip_id = f"{route_id}-{pattern_id}-{departure * 60}"
                        tables["trips.txt"].append(
                            [
                                route_id,
                                service_id,
                                trip_id,
                                pattern["direction_id"],
                                "",
                            ]
                        )
                        for sequence, (stop, offset) in enumerate(
                            zip(pattern["stops"], offsets, strict=True), start=1
                        ):
                            value = gtfs_time(departure + offset)
                            tables["stop_times.txt"].append(
                                [
                                    trip_id,
                                    value,
                                    value,
                                    stop["source_stop_id"],
                                    sequence,
                                ]
                            )
        elif dataset["kind"] == "scheduled_service":
            service = dataset["service"]
            service_id = f"scheduled-{route_id}-weekly"
            tables["calendar.txt"].append(
                [
                    service_id,
                    *(int(day in service["weekdays"]) for day in range(7)),
                    _date(service["start_date"]),
                    _date(service["end_date"]),
                ]
            )
            for pattern in dataset["patterns"]:
                pattern_id = pattern.get("pattern_id", pattern["direction_id"])
                shape_id = f"{route_id}-{pattern_id}"
                shape = pattern.get("shape") or [
                    [stop["lon"], stop["lat"]] for stop in pattern["stops"]
                ]
                if shape_id not in shape_seen:
                    for sequence, (lon, lat) in enumerate(shape, start=1):
                        tables["shapes.txt"].append([shape_id, lat, lon, sequence])
                    shape_seen.add(shape_id)
                for stop in pattern["stops"]:
                    stop_id = stop["source_stop_id"]
                    if stop_id not in stop_seen:
                        tables["stops.txt"].append(
                            [stop_id, stop["name"], stop["lat"], stop["lon"], 0, ""]
                        )
                        stop_seen.add(stop_id)
                for trip_index, trip in enumerate(pattern["trips"], start=1):
                    trip_id = f"{shape_id}-{service_id}-{trip_index}"
                    tables["trips.txt"].append(
                        [
                            route_id,
                            service_id,
                            trip_id,
                            pattern["direction_id"],
                            shape_id,
                        ]
                    )
                    for sequence, (stop, value) in enumerate(
                        zip(pattern["stops"], trip, strict=True), start=1
                    ):
                        parsed = gtfs_time(value)
                        tables["stop_times.txt"].append(
                            [trip_id, parsed, parsed, stop["source_stop_id"], sequence]
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
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("agency.txt", agency)
            for name, rows in tables.items():
                if rows:
                    archive.writestr(name, _csv_bytes(headers[name], rows))
        validate_gtfs(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
