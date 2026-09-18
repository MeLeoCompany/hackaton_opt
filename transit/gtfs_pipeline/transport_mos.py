from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from .common import write_json

BASE_URL = "https://transport.mos.ru/transport/schedule/route/{route_id}"
USER_AGENT = "hackaton-opt-gtfs/0.1 (educational transit feed builder)"


class ScheduleParseError(ValueError):
    """Официальная страница не содержит согласованного расписания маршрута."""


def fetch_route_page(route_id: int, service_date: date, direction: int) -> str:
    query = urllib.parse.urlencode(
        {
            "mgt_schedule[date]": service_date.strftime("%d.%m.%Y"),
            "mgt_schedule[route]": str(route_id),
            "mgt_schedule[direction]": str(direction),
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL.format(route_id=route_id)}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode(
                    response.headers.get_content_charset() or "utf-8"
                )
        except (OSError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"не удалось получить маршрут {route_id}, направление {direction}"
    ) from last_error


def _service_day_minutes(hour: int, minute: int, boundary_hour: int = 3) -> int:
    # Портал выводит отправления после полуночи перед строкой 05:00. В GTFS они
    # записываются как 24:xx/25:xx, чтобы время рейса всегда шло вперёд.
    if hour < boundary_hour:
        hour += 24
    return hour * 60 + minute


def _departures(stop: Tag) -> list[int]:
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
                values.append(_service_day_minutes(hour, int(minute_text)))
    return sorted(values)


def parse_route_page(html: str, *, route_id: int, service_date: date) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    route_name_node = soup.select_one("h1.h3mb")
    route_container = soup.select_one(".schedule-route[data-coords]")
    stop_nodes = soup.select(".schedule-route [data-direction][data-stop]")
    if route_name_node is None or route_container is None or not stop_nodes:
        raise ScheduleParseError(
            "отсутствуют название, геометрия или остановки маршрута"
        )

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
        departures = _departures(node)
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
    route_id: int, service_date: date, delay_seconds: float = 1.0
) -> dict[str, Any]:
    patterns = []
    route_name = None
    source_urls = []
    for direction in (0, 1):
        html = fetch_route_page(route_id, service_date, direction)
        parsed = parse_route_page(html, route_id=route_id, service_date=service_date)
        patterns.append(parsed)
        soup = BeautifulSoup(html, "html.parser")
        route_name = route_name or soup.select_one("h1.h3mb").get_text(" ", strip=True)
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
        },
        "route": {
            "source_route_id": str(route_id),
            "short_name": route_name,
            "route_type": 3,
        },
        "patterns": patterns,
    }


def collect_bus_to_file(route_id: int, service_date: date, output: Path) -> None:
    write_json(output, collect_bus_route(route_id, service_date))
