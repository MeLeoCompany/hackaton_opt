"""Импорт сохранённых HTML-расписаний автобусов в локальный набор GTFS."""

from __future__ import annotations

import re
import shutil
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .bus_weekly import prepare_bus
from .common import read_json, write_json
from .transport_mos import BASE_URL, parse_route_page


FILE_NAME = re.compile(r"^(.+?)\s+-\s+([12])\.html$", re.IGNORECASE)


def import_bus_html(
    input_dir: Path,
    archive_dir: Path,
    catalog_path: Path,
    output_dir: Path,
    start_date: date,
    end_date: date,
    inventory_path: Path | None = None,
) -> list[str]:
    """Проверить пары HTML, создать расписания и переместить исходники в архив."""
    catalog = read_json(catalog_path)
    catalog_by_id = {
        str(route["source_route_id"]): route for route in catalog["routes"]
    }
    grouped: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in sorted(input_dir.glob("*.html")):
        match = FILE_NAME.match(path.name.strip())
        if match:
            grouped[match.group(1).strip()].append((path, int(match.group(2))))
    if not grouped:
        raise ValueError(f"в {input_dir} нет файлов вида 'номер - 1.html' и 'номер - 2.html'")

    prepared: list[dict[str, Any]] = []
    for file_route_name, files in sorted(grouped.items()):
        if sorted(number for _, number in files) != [1, 2]:
            raise ValueError(f"для маршрута {file_route_name} нужны ровно два направления")
        patterns = []
        route_id: int | None = None
        service_date: date | None = None
        source_files = []
        for path, number in sorted(files, key=lambda item: item[1]):
            html = path.read_text(encoding="utf-8")
            page_route_id, page_date = _page_metadata(html, path)
            if route_id is not None and page_route_id != route_id:
                raise ValueError(f"у файлов маршрута {file_route_name} различаются ID")
            if service_date is not None and page_date != service_date:
                raise ValueError(f"у файлов маршрута {file_route_name} различаются даты")
            route_id, service_date = page_route_id, page_date
            pattern = parse_route_page(
                html, route_id=page_route_id, service_date=page_date
            )
            expected_direction = number - 1
            if pattern["direction_id"] != expected_direction:
                raise ValueError(
                    f"{path.name}: ожидалось направление {expected_direction}, "
                    f"получено {pattern['direction_id']}"
                )
            patterns.append(pattern)
            source_files.append(path)

        assert route_id is not None and service_date is not None
        catalog_route = catalog_by_id.get(str(route_id))
        if catalog_route is None:
            raise ValueError(f"маршрут {route_id} отсутствует в каталоге")
        short_name = str(catalog_route["short_name"])
        if short_name.casefold() != file_route_name.casefold():
            raise ValueError(
                f"имя файлов {file_route_name} не совпадает с каталогом: {short_name}"
            )
        prepared.append(
            {
                "route_id": route_id,
                "short_name": short_name,
                "service_date": service_date,
                "patterns": patterns,
                "source_files": source_files,
            }
        )

    for route in prepared:
        for source in route["source_files"]:
            destination = archive_dir / source.name.strip()
            if destination.exists():
                raise FileExistsError(f"архивный файл уже существует: {destination}")

    imported_names = []
    for route in prepared:
        route_id = route["route_id"]
        service_date = route["service_date"]
        exact_path = output_dir / f"route-{route_id}-{service_date.isoformat()}.json"
        write_json(
            exact_path,
            {
                "schema_version": 1,
                "kind": "bus_exact",
                "source": {
                    "publisher": "Единый транспортный портал Москвы",
                    "urls": [
                        f"{BASE_URL.format(route_id=route_id)}?"
                        + urllib.parse.urlencode(
                            {
                                "mgt_schedule[date]": service_date.strftime("%d.%m.%Y"),
                                "mgt_schedule[direction]": str(direction),
                            }
                        )
                        for direction in range(2)
                    ],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "service_date": service_date.isoformat(),
                    "night_service": False,
                    "local_html": [path.name.strip() for path in route["source_files"]],
                },
                "route": {
                    "source_route_id": str(route_id),
                    "short_name": route["short_name"],
                    "route_type": 3,
                },
                "patterns": route["patterns"],
            },
        )
        prepare_bus(
            route_id,
            route["short_name"],
            service_date,
            start_date,
            end_date,
            output_dir,
            retrospective=start_date < service_date,
        )
        imported_names.append(route["short_name"])

    archive_dir.mkdir(parents=True, exist_ok=True)
    for route in prepared:
        for source in route["source_files"]:
            destination = archive_dir / source.name.strip()
            shutil.move(source, destination)
    if inventory_path is not None:
        _update_inventory(inventory_path, imported_names)
    return imported_names


def _page_metadata(html: str, path: Path) -> tuple[int, date]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("[data-route][data-date][data-direction]")
    if node is None:
        raise ValueError(f"в {path.name} не найдены ID маршрута и дата")
    return int(str(node["data-route"])), date.fromisoformat(str(node["data-date"]))


def _update_inventory(path: Path, route_names: list[str]) -> None:
    existing = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    existing = [line for line in existing if line]
    known = {line.casefold() for line in existing}
    existing.extend(name for name in route_names if name.casefold() not in known)
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")
