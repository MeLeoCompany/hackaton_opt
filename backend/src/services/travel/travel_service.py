import logging

import httpx

from src.schemas.travel import Point, TransportKind, TravelMatrix, TravelRoute
from src.services.travel import haversine_provider, valhalla_provider

logger = logging.getLogger(__name__)


async def build_matrix(
    points: list[Point], transport: TransportKind, *, allow_fallback: bool = True
) -> TravelMatrix:
    try:
        return await valhalla_provider.build_matrix(points, transport)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        # деградация видна и в логе, и в поле provider ответа — цифры отличаются в разы
        logger.warning("Valhalla недоступна, матрица посчитана по haversine", exc_info=True)
        return haversine_provider.build_matrix(points, transport)


async def build_route(
    points: list[Point], transport: TransportKind, *, allow_fallback: bool = True
) -> TravelRoute:
    try:
        return await valhalla_provider.build_route(points, transport)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        logger.warning("Valhalla недоступна, маршрут посчитан по haversine без геометрии", exc_info=True)
        return haversine_provider.build_route(points, transport)
