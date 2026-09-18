from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

REQUIRED = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}


def validate_gtfs(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = REQUIRED - names
        if missing:
            raise ValueError(f"отсутствуют обязательные файлы GTFS: {sorted(missing)}")
        for name in names:
            if not name.endswith(".txt"):
                continue
            content = archive.read(name).decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(content)))
            if not rows:
                raise ValueError(f"файл {name} пуст")
            counts[name] = len(rows)
        trip_ids = _column(archive, "trips.txt", "trip_id")
        stop_time_trips = _column(archive, "stop_times.txt", "trip_id")
        if not stop_time_trips <= trip_ids:
            raise ValueError("stop_times.txt ссылается на неизвестные рейсы")
        stop_ids = _column(archive, "stops.txt", "stop_id")
        referenced_stops = _column(archive, "stop_times.txt", "stop_id")
        if not referenced_stops <= stop_ids:
            raise ValueError("stop_times.txt ссылается на неизвестные остановки")
        parent_stations = _column(archive, "stops.txt", "parent_station") - {""}
        if not parent_stations <= stop_ids:
            raise ValueError("stops.txt ссылается на неизвестные родительские станции")
        if "transfers.txt" in names:
            transfer_stops = _column(archive, "transfers.txt", "from_stop_id")
            transfer_stops |= _column(archive, "transfers.txt", "to_stop_id")
            if not transfer_stops <= stop_ids:
                raise ValueError("transfers.txt ссылается на неизвестные остановки")
    return counts


def _column(archive: zipfile.ZipFile, name: str, column: str) -> set[str]:
    content = archive.read(name).decode("utf-8-sig")
    return {row[column] for row in csv.DictReader(io.StringIO(content))}
