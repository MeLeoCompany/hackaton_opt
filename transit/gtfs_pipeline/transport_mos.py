from __future__ import annotations

import json
import time
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from .common import read_json, write_json

BASE_URL = "https://transport.mos.ru/transport/schedule/route/{route_id}"
NIGHT_CATALOG_URL = "https://transport.mos.ru/transport/schedule/night"
CATALOG_URL = (
    "https://transport.mos.ru/ru/ajax/App/V2_ScheduleV2Controller/getRoutesList"
)
USER_AGENT = "hackaton-opt-gtfs/0.1 (educational transit feed builder)"


class ScheduleParseError(ValueError):
    """Официальная страница не содержит согласованного расписания маршрута."""


def _fetch_text(url: str, *, timeout: int = 30) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "X-Requested-With": "XMLHttpRequest",
                },
                follow_redirects=True,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"не удалось получить данные по адресу {url}") from last_error


def fetch_route_page(route_id: int, service_date: date, direction: int) -> str:
    query = urllib.parse.urlencode(
        {
            "mgt_schedule[date]": service_date.strftime("%d.%m.%Y"),
            "mgt_schedule[route]": str(route_id),
            "mgt_schedule[direction]": str(direction),
        }
    )
    return _fetch_text(f"{BASE_URL.format(route_id=route_id)}?{query}")


def fetch_catalog_page(page: int) -> str:
    query = urllib.parse.urlencode(
        {
            "mgt_schedule[search]": "",
            "mgt_schedule[isNight]": "",
            "mgt_schedule[workTime]": "1",
            "mgt_schedule[direction]": "0",
            "page": str(page),
        }
    )
    return _fetch_text(f"{CATALOG_URL}?{query}")


def parse_catalog_page(html: str) -> tuple[list[dict[str, Any]], int]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#schedule-table")
    if table is None:
        raise ScheduleParseError("в ответе отсутствует таблица маршрутов")
    page_count = int(str(table.get("data-count-pages", "1")))
    routes: list[dict[str, Any]] = []
    for row in table.select("a.ts-row[href]"):
        href = str(row["href"])
        route_id = href.rstrip("/").rsplit("/", 1)[-1]
        number = row.select_one(".ts-number")
        title = row.select_one(".ts-title")
        columns = row.select(".ts-200")
        icon = number.select_one("i") if number else None
        if number is None or title is None or not route_id.isdigit():
            raise ScheduleParseError("не удалось разобрать строку каталога маршрутов")
        icon_classes = set(icon.get("class", [])) if icon else set()
        mode = "bus" if "ic-bus" in icon_classes else "other"
        routes.append(
            {
                "source_route_id": route_id,
                "short_name": number.get_text(" ", strip=True),
                "long_name": title.get_text(" ", strip=True),
                "mode": mode,
                "operating_hours": columns[0].get_text(" ", strip=True)
                if columns
                else "",
                "interval_summary": columns[1].get_text(" ", strip=True)
                if len(columns) > 1
                else "",
                "url": urllib.parse.urljoin(CATALOG_URL, href),
            }
        )
    if not routes:
        raise ScheduleParseError("каталог маршрутов пуст")
    return routes, page_count


def _catalog_page(page: int, cache_dir: Path | None) -> str:
    cache_path = cache_dir / f"page-{page}.html" if cache_dir else None
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    html = fetch_catalog_page(page)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
    return html


def collect_bus_catalog(
    delay_seconds: float = 1.0, cache_dir: Path | None = None
) -> dict[str, Any]:
    first_routes, page_count = parse_catalog_page(_catalog_page(1, cache_dir))
    routes = first_routes
    for page in range(2, page_count + 1):
        if delay_seconds:
            time.sleep(delay_seconds)
        page_routes, reported_page_count = parse_catalog_page(
            _catalog_page(page, cache_dir)
        )
        if reported_page_count != page_count:
            raise ScheduleParseError(
                "число страниц каталога изменилось во время загрузки"
            )
        routes.extend(page_routes)
    buses = [route for route in routes if route["mode"] == "bus"]
    route_ids = [route["source_route_id"] for route in buses]
    if len(route_ids) != len(set(route_ids)):
        raise ScheduleParseError(
            "каталог содержит повторяющиеся идентификаторы маршрутов"
        )
    return {
        "schema_version": 1,
        "kind": "bus_catalog",
        "source": {
            "publisher": "Единый транспортный портал Москвы",
            "url": "https://transport.mos.ru/transport/schedule",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "route_count": len(buses),
        "routes": buses,
    }


def collect_catalog_to_file(output: Path, cache_dir: Path | None = None) -> None:
    write_json(output, collect_bus_catalog(cache_dir=cache_dir))


def collect_night_catalog_to_file(output: Path) -> None:
    routes, page_count = parse_catalog_page(_fetch_text(NIGHT_CATALOG_URL))
    if page_count != 1 or any(route["mode"] != "bus" for route in routes):
        raise ScheduleParseError(
            "ночной каталог содержит неожиданные страницы или виды транспорта"
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "kind": "bus_catalog",
            "source": {
                "publisher": "Единый транспортный портал Москвы",
                "url": NIGHT_CATALOG_URL,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            "route_count": len(routes),
            "routes": routes,
        },
    )


def _service_day_minutes(hour: int, minute: int, boundary_hour: int = 3) -> int:
    # Портал выводит отправления после полуночи перед строкой 05:00. В GTFS они
    # записываются как 24:xx/25:xx, чтобы время рейса всегда шло вперёд.
    if hour < boundary_hour:
        hour += 24
    return hour * 60 + minute


def _departures(stop: Tag, *, boundary_hour: int = 3) -> list[int]:
    values: list[int] = []
    for row in stop.select(".raspisanie_hover .raspisanie_data"):
        hour_node = row.select_one(".dt1")
        if hour_node is None:
            continue
        hour_text = hour_node.get_text(strip=True).rstrip(":")
        if not hour_text.isdigit():
            continue
        hour = int(hour_text)
        for minute_node in row.select(".dt2 .div10"):
            minute_text = minute_node.get_text(strip=True)
            if minute_text.isdigit():
                values.append(
                    _service_day_minutes(hour, int(minute_text), boundary_hour)
                )
    return sorted(values)


def _closed_shape(coordinates: list[list[float]]) -> bool:
    """Кольцо портала иногда заканчивается рядом со стартом, но не в той же точке."""
    if len(coordinates) < 2:
        return False
    lon1, lat1 = coordinates[0][:2]
    lon2, lat2 = coordinates[-1][:2]
    return (lon1 - lon2) ** 2 + (lat1 - lat2) ** 2 < 0.01**2


def _align_trip_departures(stops: list[dict[str, Any]]) -> None:
    """Сопоставить рейсы между последовательными остановками.

    На Б/Бк портал в середине кольца снова нумерует отправления с первого рейса.
    У линейного маршрута последний рейс может прибыть ровно после границы сервисного
    дня и оказаться в начале отсортированного списка. Сдвигаем список до первого
    согласованного рейса; перенесённые через конец значения относятся к следующим суткам.
    """
    previous = stops[0]["departures"]
    for stop in stops[1:]:
        values = stop["departures"]
        aligned = None
        for shift in range(len(values)):
            candidate = values[shift:] + [value + 24 * 60 for value in values[:shift]]
            if all(
                current >= before
                for before, current in zip(previous, candidate, strict=True)
            ):
                aligned = candidate
                break
        if aligned is None:
            raise ScheduleParseError("не удалось сопоставить рейсы между остановками")
        stop["departures"] = aligned
        previous = aligned


def parse_route_page(
    html: str, *, route_id: int, service_date: date, night: bool = False
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    route_container = soup.select_one(".schedule-route[data-coords]")
    stop_nodes = soup.select(".schedule-route [data-direction][data-stop]")
    if route_container is None or not stop_nodes:
        raise ScheduleParseError("отсутствуют геометрия или остановки маршрута")

    geometry = json.loads(str(route_container["data-coords"]))
    points = [
        feature
        for feature in geometry.get("features", [])
        if feature.get("geometry", {}).get("type") == "Point"
    ]
    lines = [
        feature
        for feature in geometry.get("features", [])
        if feature.get("geometry", {}).get("type") == "LineString"
    ]
    if len(points) != len(stop_nodes) or len(lines) != 1:
        raise ScheduleParseError(
            f"ожидались одна трасса и одна точка на остановку; получено трасс: "
            f"{len(lines)}, точек: {len(points)}, остановок: {len(stop_nodes)}"
        )

    stops: list[dict[str, Any]] = []
    for position, (node, point) in enumerate(
        zip(stop_nodes, points, strict=True), start=1
    ):
        name_node = node.select_one(".sl_a .a_dotted")
        # Ночные рейсы продолжаются до утра: 03:00–11:59 относится к следующим суткам.
        departures = _departures(node, boundary_hour=12 if night else 3)
        coordinates = point["geometry"]["coordinates"]
        if name_node is None or not departures or len(coordinates) < 2:
            raise ScheduleParseError(f"неполные данные остановки в позиции {position}")
        stops.append(
            {
                "source_stop_id": str(point["id"]),
                "name": name_node.get_text(" ", strip=True),
                "lon": coordinates[0],
                "lat": coordinates[1],
                "departures": departures,
            }
        )

    trip_count = len(stops[0]["departures"])
    if any(len(stop["departures"]) != trip_count for stop in stops):
        raise ScheduleParseError("число отправлений различается между остановками")
    _align_trip_departures(stops)
    for trip_index in range(trip_count):
        trip_times = [stop["departures"][trip_index] for stop in stops]
        if trip_times != sorted(trip_times):
            raise ScheduleParseError(f"время рейса {trip_index} движется назад")

    direction = int(str(stop_nodes[0]["data-direction"]))
    return {
        "direction_id": direction,
        "stops": stops,
        "shape": lines[0]["geometry"]["coordinates"],
    }


def collect_bus_route(
    route_id: int,
    service_date: date,
    delay_seconds: float = 1.0,
    route_name: str | None = None,
    night: bool = False,
) -> dict[str, Any]:
    patterns = []
    source_urls = []
    for direction in (0, 1):
        html = fetch_route_page(route_id, service_date, direction)
        try:
            parsed = parse_route_page(
                html, route_id=route_id, service_date=service_date, night=night
            )
        except ScheduleParseError:
            # У кольцевых Б/Бк на портале существует только direction=0. Обычный
            # маршрут без второго направления по-прежнему считается неполным.
            if (
                direction == 1
                and len(patterns) == 1
                and _closed_shape(patterns[0]["shape"])
            ):
                continue
            raise
        patterns.append(parsed)
        soup = BeautifulSoup(html, "html.parser")
        page_route_name = soup.select_one("h1.h3mb")
        if route_name is None and page_route_name is not None:
            route_name = page_route_name.get_text(" ", strip=True)
        source_urls.append(
            f"{BASE_URL.format(route_id=route_id)}?"
            + urllib.parse.urlencode(
                {
                    "mgt_schedule[date]": service_date.strftime("%d.%m.%Y"),
                    "mgt_schedule[direction]": str(direction),
                }
            )
        )
        if direction == 0 and delay_seconds:
            time.sleep(delay_seconds)
    return {
        "schema_version": 1,
        "kind": "bus_exact",
        "source": {
            "publisher": "Единый транспортный портал Москвы",
            "urls": source_urls,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "service_date": service_date.isoformat(),
            "night_service": night,
        },
        "route": {
            "source_route_id": str(route_id),
            "short_name": route_name or str(route_id),
            "route_type": 3,
        },
        "patterns": patterns,
    }


def collect_bus_to_file(
    route_id: int,
    service_date: date,
    output: Path,
    route_name: str | None = None,
    night: bool = False,
) -> None:
    write_json(
        output,
        collect_bus_route(route_id, service_date, route_name=route_name, night=night),
    )


def collect_bus_batch(
    route_ids: list[int],
    service_dates: list[date],
    output_dir: Path,
    catalog_path: Path | None = None,
    night: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    route_names: dict[int, str] = {}
    if catalog_path:
        catalog = read_json(catalog_path)
        route_names = {
            int(route["source_route_id"]): route["short_name"]
            for route in catalog["routes"]
        }
        missing = sorted(set(route_ids) - route_names.keys())
        if missing:
            raise ValueError(f"маршруты отсутствуют в каталоге: {missing}")
    results: list[dict[str, Any]] = []
    for route_id in route_ids:
        for service_date in service_dates:
            output = output_dir / f"route-{route_id}-{service_date.isoformat()}.json"
            try:
                collect_bus_to_file(
                    route_id,
                    service_date,
                    output,
                    route_name=route_names.get(route_id),
                    night=night,
                )
                results.append(
                    {
                        "route_id": route_id,
                        "service_date": service_date.isoformat(),
                        "status": "ok",
                        "output": str(output),
                    }
                )
            except Exception as error:  # noqa: BLE001 - пакетный сбор должен продолжаться
                results.append(
                    {
                        "route_id": route_id,
                        "service_date": service_date.isoformat(),
                        "status": "error",
                        "error": str(error),
                    }
                )
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested": len(route_ids) * len(service_dates),
        "successful": sum(result["status"] == "ok" for result in results),
        "failed": sum(result["status"] == "error" for result in results),
        "results": results,
    }
    write_json(output_dir / "collection-report.json", report)
    return report
