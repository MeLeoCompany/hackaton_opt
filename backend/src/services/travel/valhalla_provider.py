"""Расстояния, время в пути и геометрия маршрутов от self-hosted Valhalla."""

import asyncio

import httpx

from src.core.config import settings
from src.schemas.travel import Point, TransportKind, TravelMatrix, TravelProvider, TravelRoute

# профиль движения Valhalla для каждого нашего транспорта.
# Расписаний ОТ (GTFS) у Valhalla нет: "bus" едет по дорогам как автобус,
# а ожидание на остановке добавляем сами (PUBLIC_TRANSPORT_WAIT_MIN)
COSTING: dict[TransportKind, str] = {
    TransportKind.CAR: "auto",
    TransportKind.PEDESTRIAN: "pedestrian",
    TransportKind.BICYCLE: "bicycle",
    TransportKind.PUBLIC_TRANSPORT: "bus",
}

PUBLIC_TRANSPORT_WAIT_MIN = 10.0

# лимиты Valhalla по умолчанию (service_limits в valhalla.json). Большие запросы режем
# на части здесь, а не поднимаем лимиты на сервере — так работает с любым инстансом.
MAX_MATRIX_PAIRS = 2500
MAX_ROUTE_LOCATIONS = 20


def _to_valhalla_locations(points: list[Point]) -> list[dict[str, float]]:
    return [{"lat": point.latitude, "lon": point.longitude} for point in points]


def _waiting_minutes(transport: TransportKind) -> float:
    """Сколько минут добавляется к каждому переезду на ожидание транспорта."""
    return PUBLIC_TRANSPORT_WAIT_MIN if transport is TransportKind.PUBLIC_TRANSPORT else 0.0


def _split_indices(total: int, block_size: int) -> list[list[int]]:
    """Делит номера 0..total-1 на подряд идущие куски не длиннее block_size."""
    return [
        list(range(block_start, min(block_start + block_size, total)))
        for block_start in range(0, total, block_size)
    ]


def _split_route(points: list[Point], max_points: int) -> list[list[Point]]:
    """Режет длинный маршрут на куски; соседние куски делят общую точку, чтобы стыковаться."""
    if len(points) <= max_points:
        return [points]
    pieces: list[list[Point]] = []
    piece_start = 0
    while piece_start < len(points) - 1:
        piece_end = min(piece_start + max_points, len(points))
        pieces.append(points[piece_start:piece_end])
        piece_start = piece_end - 1
    return pieces


async def _request_matrix_block(
    client: httpx.AsyncClient,
    points: list[Point],
    from_indices: list[int],
    to_indices: list[int],
    costing: str,
) -> tuple[list[int], list[int], list[list[dict]]]:
    """Запрашивает у Valhalla кусок матрицы: из точек from_indices во все точки to_indices."""
    payload = {
        "sources": _to_valhalla_locations([points[index] for index in from_indices]),
        "targets": _to_valhalla_locations([points[index] for index in to_indices]),
        "costing": costing,
        "units": "kilometers",
    }
    response = await client.post("/sources_to_targets", json=payload)
    response.raise_for_status()
    return from_indices, to_indices, response.json()["sources_to_targets"]


async def build_matrix(points: list[Point], transport: TransportKind) -> TravelMatrix:
    """Матрица «из каждой точки в каждую»: километры и минуты для всех пар точек.

    Матрица целиком не влезает в один запрос, поэтому запрашивается кусками параллельно
    и собирается обратно по номерам точек.
    """
    size = len(points)
    block_size = max(int(MAX_MATRIX_PAIRS**0.5), 1)
    costing = COSTING[transport]
    waiting_minutes = _waiting_minutes(transport)

    distances_km: list[list[float | None]] = [[0.0] * size for _ in range(size)]
    durations_min: list[list[float | None]] = [[0.0] * size for _ in range(size)]

    async with httpx.AsyncClient(base_url=settings.valhalla_url, timeout=180.0) as client:
        blocks = await asyncio.gather(
            *(
                _request_matrix_block(client, points, from_indices, to_indices, costing)
                for from_indices in _split_indices(size, block_size)
                for to_indices in _split_indices(size, block_size)
            )
        )

    for from_indices, to_indices, block_rows in blocks:
        for position_in_block, block_row in enumerate(block_rows):
            from_index = from_indices[position_in_block]
            for pair in block_row:
                to_index = to_indices[pair["to_index"]]
                if from_index == to_index:
                    continue
                # если между точками нет дороги, Valhalla отдаёт null
                if pair.get("time") is None or pair.get("distance") is None:
                    distances_km[from_index][to_index] = None
                    durations_min[from_index][to_index] = None
                    continue
                distances_km[from_index][to_index] = round(float(pair["distance"]), 3)
                durations_min[from_index][to_index] = float(pair["time"]) / 60 + waiting_minutes

    return TravelMatrix(
        transport=transport,
        provider=TravelProvider.VALHALLA,
        points=points,
        distances_km=distances_km,
        durations_min=durations_min,
    )


async def build_route(points: list[Point], transport: TransportKind) -> TravelRoute:
    """Маршрут через точки по порядку: километры, минуты и линия для карты.

    Линия приходит как encoded polyline с точностью 6 знаков — по одной на каждый участок.
    """
    costing = COSTING[transport]
    distance_km = 0.0
    duration_min = 0.0
    geometry: list[str] = []

    async with httpx.AsyncClient(base_url=settings.valhalla_url, timeout=120.0) as client:
        for piece in _split_route(points, MAX_ROUTE_LOCATIONS):
            payload = {
                "locations": _to_valhalla_locations(piece),
                "costing": costing,
                "units": "kilometers",
            }
            response = await client.post("/route", json=payload)
            response.raise_for_status()
            trip = response.json()["trip"]
            distance_km += float(trip["summary"]["length"])
            duration_min += float(trip["summary"]["time"]) / 60
            geometry.extend(leg["shape"] for leg in trip["legs"])

    duration_min += _waiting_minutes(transport) * max(len(points) - 1, 0)
    return TravelRoute(
        transport=transport,
        provider=TravelProvider.VALHALLA,
        distance_km=round(distance_km, 3),
        duration_min=round(duration_min, 1),
        geometry=geometry,
    )
