import logging
from datetime import datetime

import httpx

from src.core.local_day import local_timezone
from src.schemas.travel import (
    Point,
    TransportKind,
    TravelLeg,
    TravelMatrix,
    TravelProvider,
    TravelRoute,
)
from src.services.travel import (
    haversine_provider,
    r5_provider,
    transit_provider,
    valhalla_provider,
)

logger = logging.getLogger(__name__)


async def build_matrix(
    points: list[Point],
    transport: TransportKind,
    *,
    departure_time: datetime | None = None,
    allow_fallback: bool = True,
) -> TravelMatrix:
    if transport is TransportKind.PUBLIC_TRANSPORT:
        return await _public_transport_matrix(
            points,
            departure_time or datetime.now(local_timezone()),
            allow_fallback=allow_fallback,
        )

    try:
        matrix = await valhalla_provider.build_matrix(points, transport)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        # деградация видна и в логе, и в поле provider ответа — цифры отличаются в разы
        logger.warning("Valhalla недоступна, матрица посчитана по haversine", exc_info=True)
        matrix = haversine_provider.build_matrix(points, transport)

    return matrix


async def _public_transport_matrix(
    points: list[Point], departure_time: datetime, *, allow_fallback: bool
) -> TravelMatrix:
    try:
        surface = await valhalla_provider.build_matrix(
            points, TransportKind.PUBLIC_TRANSPORT
        )
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        logger.warning(
            "Valhalla недоступна, расстояния общественного транспорта оценены по прямой",
            exc_info=True,
        )
        surface = haversine_provider.build_matrix(
            points, TransportKind.PUBLIC_TRANSPORT
        )

    try:
        durations = await r5_provider.build_duration_matrix(points, departure_time)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        logger.warning(
            "R5 недоступен, использована приближённая модель общественного транспорта",
            exc_info=True,
        )
        walking = await _walking_matrix(points)
        fallback = transit_provider.matrix_with_transit(surface, walking)
        return fallback.model_copy(update={"provider": TravelProvider.TRANSIT_ESTIMATE})

    distances = [list(row) for row in surface.distances_km]
    approximate_distances: list[list[float | None]] | None = None
    for row_index, row in enumerate(durations):
        for column_index, duration in enumerate(row):
            if duration is None:
                distances[row_index][column_index] = None
            elif distances[row_index][column_index] is None:
                if approximate_distances is None:
                    approximate_distances = haversine_provider.build_matrix(
                        points, TransportKind.PUBLIC_TRANSPORT
                    ).distances_km
                distances[row_index][column_index] = approximate_distances[row_index][
                    column_index
                ]
    return TravelMatrix(
        transport=TransportKind.PUBLIC_TRANSPORT,
        provider=TravelProvider.R5,
        points=points,
        distances_km=distances,
        durations_min=durations,
    )


async def build_route(
    points: list[Point], transport: TransportKind, *, allow_fallback: bool = True
) -> TravelRoute:
    try:
        legs = await valhalla_provider.route_legs(points, transport)
        provider = TravelProvider.VALHALLA
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        logger.warning(
            "Valhalla недоступна, маршрут посчитан по haversine без геометрии", exc_info=True
        )
        legs = haversine_provider.route_legs(points, transport)
        provider = TravelProvider.HAVERSINE

    if transport is TransportKind.PUBLIC_TRANSPORT:
        legs = transit_provider.legs_with_transit(points, legs, await _walking_legs(points))

    return _route_of(legs, transport, provider)


async def _walking_matrix(points: list[Point]) -> TravelMatrix | None:
    """Пешеходная матрица для общественного транспорта; None — если Valhalla её не дала.

    Без неё пешие куски считаются по прямой линии — грубее, но расчёт дня не срывается.
    """
    try:
        return await valhalla_provider.build_matrix(points, TransportKind.PEDESTRIAN)
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("Пешие участки посчитаны по прямой: Valhalla не дала пешеходную матрицу")
        return None


async def _walking_legs(points: list[Point]) -> list[TravelLeg] | None:
    try:
        return await valhalla_provider.route_legs(points, TransportKind.PEDESTRIAN)
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("Пешие участки посчитаны по прямой: Valhalla не дала пешеходный маршрут")
        return None


def _route_of(
    legs: list[TravelLeg], transport: TransportKind, provider: TravelProvider
) -> TravelRoute:
    geometry = [leg.geometry for leg in legs]
    return TravelRoute(
        transport=transport,
        provider=provider,
        distance_km=round(sum(leg.distance_km for leg in legs), 3),
        duration_min=round(sum(leg.duration_min for leg in legs), 1),
        # без геометрии (haversine) фронт рисует прямые сам по координатам точек
        geometry=geometry if any(geometry) else [],
        legs=legs,
    )
