import logging

import httpx

from src.schemas.travel import (
    Point,
    TransportKind,
    TravelLeg,
    TravelMatrix,
    TravelProvider,
    TravelRoute,
)
from src.services.travel import haversine_provider, transit_provider, valhalla_provider

logger = logging.getLogger(__name__)


async def build_matrix(
    points: list[Point], transport: TransportKind, *, allow_fallback: bool = True
) -> TravelMatrix:
    try:
        matrix = await valhalla_provider.build_matrix(points, transport)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        # деградация видна и в логе, и в поле provider ответа — цифры отличаются в разы
        logger.warning("Valhalla недоступна, матрица посчитана по haversine", exc_info=True)
        matrix = haversine_provider.build_matrix(points, transport)

    if transport is not TransportKind.PUBLIC_TRANSPORT:
        return matrix
    # метро в дорожном графе отсутствует, а короткие куски человек проходит пешком:
    # и то и другое добавляется поверх наземного расчёта там, где оно быстрее
    return transit_provider.matrix_with_transit(matrix, await _walking_matrix(points))


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
