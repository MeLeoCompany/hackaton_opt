from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

SAME_NAME_RADIUS_METERS = 700
TRANSFER_RADIUS_METERS = 300
TRANSFER_TIME_SECONDS = 300


@dataclass
class MetroStop:
    stop_id: str
    name: str
    lat: float
    lon: float
    routes: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class StationCluster:
    station_id: str
    name: str
    lat: float
    lon: float
    stop_ids: tuple[str, ...]
    routes: tuple[str, ...]

    @property
    def is_transfer(self) -> bool:
        return len(self.routes) > 1 and len(self.stop_ids) > 1


def _normalized_name(value: str) -> str:
    return re.sub(r"[^0-9а-яёa-z]+", "", value.casefold())


def _distance_meters(left: MetroStop, right: MetroStop) -> float:
    lat1 = math.radians(left.lat)
    lat2 = math.radians(right.lat)
    dlat = lat2 - lat1
    dlon = math.radians(right.lon - left.lon)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _metro_stops(datasets: list[dict[str, Any]]) -> dict[str, MetroStop]:
    result: dict[str, MetroStop] = {}
    for dataset in datasets:
        if dataset["kind"] != "metro_frequency":
            continue
        route_id = dataset["route"]["source_route_id"]
        for pattern in dataset["patterns"]:
            for source in pattern["stops"]:
                stop = result.setdefault(
                    source["source_stop_id"],
                    MetroStop(
                        stop_id=source["source_stop_id"],
                        name=source["name"],
                        lat=source["lat"],
                        lon=source["lon"],
                    ),
                )
                stop.routes.add(route_id)
    return result


def cluster_metro_stations(datasets: list[dict[str, Any]]) -> list[StationCluster]:
    stops = list(_metro_stops(datasets).values())
    parent = list(range(len(stops)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(stops):
        for right_index in range(left_index + 1, len(stops)):
            right = stops[right_index]
            if left.routes & right.routes:
                continue
            radius = (
                SAME_NAME_RADIUS_METERS
                if _normalized_name(left.name) == _normalized_name(right.name)
                else TRANSFER_RADIUS_METERS
            )
            if _distance_meters(left, right) <= radius:
                union(left_index, right_index)

    grouped: defaultdict[int, list[MetroStop]] = defaultdict(list)
    for index, stop in enumerate(stops):
        grouped[find(index)].append(stop)

    clusters = []
    for members in grouped.values():
        stop_ids = tuple(sorted(item.stop_id for item in members))
        digest = hashlib.sha256("\n".join(stop_ids).encode()).hexdigest()[:12]
        names = sorted({item.name for item in members})
        routes = tuple(sorted({route for item in members for route in item.routes}))
        clusters.append(
            StationCluster(
                station_id=f"metro-station-{digest}",
                name=" / ".join(names),
                lat=sum(item.lat for item in members) / len(members),
                lon=sum(item.lon for item in members) / len(members),
                stop_ids=stop_ids,
                routes=routes,
            )
        )
    return sorted(clusters, key=lambda item: item.station_id)


def transfer_rows(clusters: list[StationCluster]) -> list[list[Any]]:
    rows = []
    for cluster in clusters:
        if not cluster.is_transfer:
            continue
        for source in cluster.stop_ids:
            for target in cluster.stop_ids:
                if source != target:
                    rows.append([source, target, 2, TRANSFER_TIME_SECONDS])
    return rows
