import asyncio

import httpx

from src.core.config import settings
from src.schemas.travel import Point, TransportKind, TravelMatrix, TravelProvider, TravelRoute

# ОТ у Valhalla без GTFS расписаний нет: costing "bus" едет по дорогам как автобус,
# ожидание на остановке добавляем сами (см. PUBLIC_TRANSPORT_WAIT_MIN)
COSTING: dict[TransportKind, str] = {
    TransportKind.CAR: "auto",
    TransportKind.PEDESTRIAN: "pedestrian",
    TransportKind.BICYCLE: "bicycle",
    TransportKind.PUBLIC_TRANSPORT: "bus",
}

PUBLIC_TRANSPORT_WAIT_MIN = 10.0

# дефолтные лимиты Valhalla (service_limits в valhalla.json). Запрос режем на блоки
# здесь, а не поднимаем лимиты на сервере, чтобы работало с любым инстансом «из коробки».
MAX_MATRIX_PAIRS = 2500
MAX_ROUTE_LOCATIONS = 20


def _locations(points: list[Point]) -> list[dict[str, float]]:
    return [{"lat": p.latitude, "lon": p.longitude} for p in points]


def _wait_penalty(transport: TransportKind) -> float:
    return PUBLIC_TRANSPORT_WAIT_MIN if transport is TransportKind.PUBLIC_TRANSPORT else 0.0


def _index_blocks(count: int, size: int) -> list[list[int]]:
    return [list(range(start, min(start + size, count))) for start in range(0, count, size)]


def _route_windows(points: list[Point], limit: int) -> list[list[Point]]:
    """Режет маршрут на окна, соседние окна делят общую точку — чтобы участки состыковались."""
    if len(points) <= limit:
        return [points]
    windows: list[list[Point]] = []
    start = 0
    while start < len(points) - 1:
        end = min(start + limit, len(points))
        windows.append(points[start:end])
        start = end - 1
    return windows


async def _matrix_block(
    client: httpx.AsyncClient,
    points: list[Point],
    rows: list[int],
    cols: list[int],
    costing: str,
) -> tuple[list[int], list[int], list[list[dict]]]:
    payload = {
        "sources": _locations([points[i] for i in rows]),
        "targets": _locations([points[j] for j in cols]),
        "costing": costing,
        "units": "kilometers",
    }
    response = await client.post("/sources_to_targets", json=payload)
    response.raise_for_status()
    return rows, cols, response.json()["sources_to_targets"]


async def build_matrix(points: list[Point], transport: TransportKind) -> TravelMatrix:
    size = len(points)
    block_side = max(int(MAX_MATRIX_PAIRS**0.5), 1)
    costing = COSTING[transport]
    penalty = _wait_penalty(transport)

    distances_km = [[0.0] * size for _ in range(size)]
    durations_min = [[0.0] * size for _ in range(size)]

    async with httpx.AsyncClient(base_url=settings.valhalla_url, timeout=180.0) as client:
        blocks = await asyncio.gather(
            *(
                _matrix_block(client, points, rows, cols, costing)
                for rows in _index_blocks(size, block_side)
                for cols in _index_blocks(size, block_side)
            )
        )

    for rows, cols, response_rows in blocks:
        for local_i, response_row in enumerate(response_rows):
            i = rows[local_i]
            for cell in response_row:
                j = cols[cell["to_index"]]
                if i == j:
                    continue
                # недостижимую пару Valhalla отдаёт как null
                if cell.get("time") is None or cell.get("distance") is None:
                    distances_km[i][j] = float("inf")
                    durations_min[i][j] = float("inf")
                    continue
                distances_km[i][j] = round(float(cell["distance"]), 3)
                durations_min[i][j] = round(float(cell["time"]) / 60 + penalty, 1)

    return TravelMatrix(
        transport=transport,
        provider=TravelProvider.VALHALLA,
        points=points,
        distances_km=distances_km,
        durations_min=durations_min,
    )


async def build_route(points: list[Point], transport: TransportKind) -> TravelRoute:
    costing = COSTING[transport]
    distance_km = 0.0
    duration_min = 0.0
    geometry: list[str] = []

    async with httpx.AsyncClient(base_url=settings.valhalla_url, timeout=120.0) as client:
        for window in _route_windows(points, MAX_ROUTE_LOCATIONS):
            payload = {"locations": _locations(window), "costing": costing, "units": "kilometers"}
            response = await client.post("/route", json=payload)
            response.raise_for_status()
            trip = response.json()["trip"]
            distance_km += float(trip["summary"]["length"])
            duration_min += float(trip["summary"]["time"]) / 60
            # encoded polyline точности 6 — Leaflet рисует её напрямую
            geometry.extend(leg["shape"] for leg in trip["legs"])

    duration_min += _wait_penalty(transport) * max(len(points) - 1, 0)
    return TravelRoute(
        transport=transport,
        provider=TravelProvider.VALHALLA,
        distance_km=round(distance_km, 3),
        duration_min=round(duration_min, 1),
        geometry=geometry,
    )
