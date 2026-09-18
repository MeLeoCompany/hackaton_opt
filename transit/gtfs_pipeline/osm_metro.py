from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .common import write_json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "hackaton-opt-gtfs/0.1 (educational transit feed builder)"
OFFICIAL_HOURS_URL = "https://transport.mos.ru/metro/rezhim"


def fetch_line(relations: list[int]) -> dict[str, Any]:
    relation_ids = ",".join(str(value) for value in relations)
    query = f"[out:json][timeout:90];rel(id:{relation_ids});out body;>;out body qt;"
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(
        OVERPASS_URL,
        data=body,
        headers={"User-Agent": USER_AGENT},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (OSError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(
        "не удалось получить топологию метро из Overpass"
    ) from last_error


def _duration_minutes(value: str) -> int:
    hours, minutes = (int(part) for part in value.split(":"))
    return hours * 60 + minutes


def normalize_line(raw: dict[str, Any], *, relation_ids: list[int]) -> dict[str, Any]:
    by_key = {(item["type"], item["id"]): item for item in raw["elements"]}
    relations = [by_key[("relation", relation_id)] for relation_id in relation_ids]
    patterns = []
    for direction, relation in enumerate(relations):
        stops = []
        for member in relation["members"]:
            if not member.get("role", "").startswith("stop"):
                continue
            node = by_key.get((member["type"], member["ref"]))
            if node is None or "lat" not in node or "lon" not in node:
                continue
            tags = node.get("tags", {})
            stops.append(
                {
                    "source_stop_id": f"osm-node-{node['id']}",
                    "name": tags.get("name", tags.get("name:ru", f"OSM {node['id']}")),
                    "lat": node["lat"],
                    "lon": node["lon"],
                }
            )
        tags = relation["tags"]
        patterns.append(
            {
                "direction_id": direction,
                "headsign": tags["to"],
                "duration_minutes": _duration_minutes(tags["duration"]),
                "stops": stops,
            }
        )
    tags = relations[0]["tags"]
    today = datetime.now(timezone.utc).date()
    return {
        "schema_version": 1,
        "kind": "metro_frequency",
        "source": {
            "topology": "OpenStreetMap через Overpass API (ODbL)",
            "topology_url": "https://www.openstreetmap.org/",
            "relation_ids": relation_ids,
            "operating_hours": "Единый транспортный портал Москвы",
            "operating_hours_url": OFFICIAL_HOURS_URL,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "route": {
            "source_route_id": f"metro-{tags['ref']}",
            "short_name": tags["ref"],
            "long_name": tags.get("name", "").split(":", 1)[0],
            "route_type": 1,
            "color": tags.get("colour", "").lstrip("#"),
        },
        "service": {
            "start_date": today.isoformat(),
            "end_date": date(today.year, 12, 31).isoformat(),
            "daily": True,
            "official_operating_window": ["05:30:00", "25:00:00"],
            "headways": [
                {"start": "05:30:00", "end": "06:30:00", "seconds": 300},
                {"start": "06:30:00", "end": "10:00:00", "seconds": 120},
                {"start": "10:00:00", "end": "16:00:00", "seconds": 180},
                {"start": "16:00:00", "end": "20:00:00", "seconds": 120},
                {"start": "20:00:00", "end": "23:00:00", "seconds": 180},
                {"start": "23:00:00", "end": "25:00:00", "seconds": 300},
            ],
            "headway_note": "Расчётное приближение, не официальное расписание поездов.",
        },
        "patterns": patterns,
    }


def collect_metro_to_file(relation_ids: list[int], output: Path) -> None:
    write_json(
        output, normalize_line(fetch_line(relation_ids), relation_ids=relation_ids)
    )
