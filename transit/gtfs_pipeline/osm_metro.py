from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .common import write_json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "hackaton-opt-gtfs/0.1 (educational transit feed builder)"
OFFICIAL_HOURS_URL = "https://transport.mos.ru/metro/rezhim"
MOSCOW_METRO_WIKIDATA = "Q5499"


class MetroDataError(ValueError):
    """В исходных данных метро отсутствуют обязательные сведения."""


def _overpass(query: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=120,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError("не удалось получить топологию метро из Overpass") from last_error


def discover_lines(raw: dict[str, Any] | None = None) -> dict[str, list[int]]:
    query = (
        '[out:json][timeout:90];(rel["route"="subway"]'
        f'["network:wikidata"="{MOSCOW_METRO_WIKIDATA}"];'
        'rel["route"="subway"]["network"="Московский метрополитен"];);out tags;'
    )
    raw = raw or _overpass(query)
    grouped: defaultdict[str, list[int]] = defaultdict(list)
    for element in raw["elements"]:
        ref = element.get("tags", {}).get("ref")
        if ref:
            grouped[ref].append(element["id"])
    if not grouped:
        raise MetroDataError("в Overpass не найдены линии Московского метрополитена")
    return {ref: sorted(ids) for ref, ids in grouped.items()}


def fetch_line(relations: list[int]) -> dict[str, Any]:
    relation_ids = ",".join(str(value) for value in relations)
    query = f"[out:json][timeout:90];rel(id:{relation_ids});out body;>;out body qt;"
    return _overpass(query)


def _duration_minutes(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise MetroDataError(f"неподдерживаемая длительность поездки: {value}")


def _line_filename(ref: str) -> str:
    return f"line-{_normalized_ref(ref)}.json"


def _normalized_ref(ref: str) -> str:
    normalized = ref.lower().replace("а", "a")
    return re.sub(r"[^0-9a-zа-яё]+", "-", normalized).strip("-")


def normalize_line(raw: dict[str, Any], *, relation_ids: list[int]) -> dict[str, Any]:
    by_key = {(item["type"], item["id"]): item for item in raw["elements"]}
    try:
        relations = [by_key[("relation", relation_id)] for relation_id in relation_ids]
    except KeyError as error:
        raise MetroDataError(f"отношение OSM отсутствует в ответе: {error}") from error
    if len(relations) != 2:
        raise MetroDataError(
            f"ожидалось два направления линии, получено {len(relations)}"
        )

    refs = {relation.get("tags", {}).get("ref") for relation in relations}
    if len(refs) != 1 or None in refs:
        raise MetroDataError(f"отношения относятся к разным линиям: {sorted(refs)}")

    patterns = []
    duration_estimated = False
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
                    "source_stop_id": f"osm-{member['type']}-{node['id']}",
                    "name": tags.get("name:ru", tags.get("name", f"OSM {node['id']}")),
                    "lat": node["lat"],
                    "lon": node["lon"],
                }
            )
        if len(stops) < 2:
            raise MetroDataError(
                f"в отношении {relation['id']} найдено меньше двух остановок"
            )
        tags = relation["tags"]
        duration = tags.get("duration")
        if duration is None:
            duration_estimated = True
            duration_minutes = max(1, (len(stops) - 1) * 3)
        else:
            duration_minutes = _duration_minutes(duration)
        patterns.append(
            {
                "pattern_id": str(relation["id"]),
                "direction_id": direction,
                "headsign": tags.get("to", tags.get("name", f"Направление {direction + 1}")),
                "duration_minutes": duration_minutes,
                "duration_estimated": duration is None,
                "stops": stops,
            }
        )

    tags = relations[0]["tags"]
    today = datetime.now(timezone.utc).date()
    route_name = tags.get("name", "").split(":", 1)[0].split(" (", 1)[0]
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
            "source_route_id": f"metro-{_normalized_ref(tags['ref'])}",
            "short_name": tags["ref"],
            "long_name": route_name,
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
            "duration_note": (
                "Для отношений без duration принято 3 минуты на перегон."
                if duration_estimated
                else "Длительность всей поездки взята из отношения OSM."
            ),
        },
        "patterns": patterns,
    }


def collect_metro_to_file(relation_ids: list[int], output: Path) -> None:
    write_json(output, normalize_line(fetch_line(relation_ids), relation_ids=relation_ids))


def _cached_overpass(cache_path: Path, query: str) -> dict[str, Any]:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    raw = _overpass(query)
    write_json(cache_path, raw)
    return raw


def collect_metro_network(output_dir: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    if cache_dir is None:
        discovered = discover_lines()
    else:
        discovery_query = (
            '[out:json][timeout:90];(rel["route"="subway"]'
            f'["network:wikidata"="{MOSCOW_METRO_WIKIDATA}"];'
            'rel["route"="subway"]["network"="Московский метрополитен"];);'
            "out tags;"
        )
        discovery = _cached_overpass(cache_dir / "relations.json", discovery_query)
        discovered = discover_lines(discovery)
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for ref in sorted(discovered, key=lambda value: (len(value), value)):
        relation_ids = discovered[ref]
        fetched_from_network = cache_dir is None
        if cache_dir is None:
            raw = fetch_line(relation_ids)
        else:
            relation_list = ",".join(str(value) for value in relation_ids)
            query = (
                f"[out:json][timeout:90];rel(id:{relation_list});"
                "out body;>;out body qt;"
            )
            cache_path = cache_dir / f"line-{ref}.json"
            fetched_from_network = not cache_path.exists()
            raw = _cached_overpass(cache_path, query)
        dataset = normalize_line(raw, relation_ids=relation_ids)
        filename = _line_filename(ref)
        write_json(output_dir / filename, dataset)
        lines.append(
            {
                "ref": ref,
                "name": dataset["route"]["long_name"],
                "file": filename,
                "relation_ids": relation_ids,
                "stops_by_direction": [len(item["stops"]) for item in dataset["patterns"]],
                "duration_estimated": any(
                    item["duration_estimated"] for item in dataset["patterns"]
                ),
            }
        )
        if fetched_from_network:
            time.sleep(1)
    manifest = {
        "schema_version": 1,
        "kind": "metro_network_manifest",
        "source": "OpenStreetMap через Overpass API (ODbL)",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "line_count": len(lines),
        "lines": lines,
    }
    write_json(output_dir / "network.json", manifest)
    return manifest
