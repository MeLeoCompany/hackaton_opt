import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import pairwise

import httpx

from src.core import clock
from src.core.local_day import local_timezone
from src.schemas.travel import (
    Point,
    TransportKind,
    TravelLeg,
    TravelMatrix,
    TravelProvider,
    TravelRoute,
)
from src.services.planner import run_log
from src.services.travel import (
    haversine_provider,
    r5_access,
    r5_provider,
    transit_provider,
    travel_cache,
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
            departure_time or clock.now().astimezone(local_timezone()),
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
    await run_log.note("ОТ: расстояния по улицам (Valhalla)")
    try:
        surface = await valhalla_provider.build_matrix(points, TransportKind.PUBLIC_TRANSPORT)
    except (httpx.HTTPError, KeyError, ValueError):
        if not allow_fallback:
            raise
        logger.warning(
            "Valhalla недоступна, расстояния общественного транспорта оценены по прямой",
            exc_info=True,
        )
        surface = haversine_provider.build_matrix(points, TransportKind.PUBLIC_TRANSPORT)

    await run_log.note("ОТ: времена по расписанию (R5)")
    try:
        durations = await _r5_durations(points, departure_time)
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
                distances[row_index][column_index] = approximate_distances[row_index][column_index]

    await run_log.note("ОТ: пешие подходы (Valhalla)")
    walking = await _walking_matrix(points)
    if walking is not None:
        for row_index, row in enumerate(durations):
            for column_index, duration in enumerate(row):
                walk_duration = walking.durations_min[row_index][column_index]
                walk_distance = walking.distances_km[row_index][column_index]
                if (
                    walk_duration is not None
                    and walk_distance is not None
                    and (duration is None or walk_duration <= duration)
                ):
                    durations[row_index][column_index] = walk_duration
                    distances[row_index][column_index] = walk_distance
    return TravelMatrix(
        transport=TransportKind.PUBLIC_TRANSPORT,
        provider=TravelProvider.R5,
        points=points,
        distances_km=distances,
        durations_min=durations,
    )


async def _r5_durations(points: list[Point], departure_time: datetime) -> list[list[float | None]]:
    """Минуты R5 по расписанию для всех пар точек: из кеша, недостающие — у R5.

    Недостающие пары покрываются как можно меньшим числом точек: для них R5 считает строки
    «эти точки × все» и столбцы «все × эти точки». Потом — тот же досчёт изолированных
    точек, что и без кеша, и новые пары ложатся в кеш (docs/algoCachV1.md).
    """
    size = len(points)
    known = await travel_cache.load_matrix(points, departure_time)
    if not known:
        await run_log.note(f"R5: в кеше пар нет — считаю матрицу целиком ({size * (size - 1)} пар)")
        durations = await r5_provider.build_duration_matrix(points, departure_time)
        durations = await r5_access.repair_duration_matrix(points, departure_time, durations)
        await travel_cache.save_matrix(
            points,
            departure_time,
            durations,
            ((i, j) for i in range(size) for j in range(size) if i != j),
        )
        return durations

    durations: list[list[float | None]] = [
        [0.0 if i == j else known.get((i, j)) for j in range(size)] for i in range(size)
    ]
    missing = {(i, j) for i in range(size) for j in range(size) if i != j and (i, j) not in known}
    total = size * (size - 1)
    if not missing:
        await run_log.note(f"R5: все {total} пар матрицы из кеша — R5 для матрицы не нужен")
    else:
        rows = covering_points(missing)
        others = [index for index in range(size) if index not in rows]
        await run_log.note(
            f"R5: пар из кеша {total - len(missing)} из {total}, досчитываю {len(missing)} — "
            f"строки и столбцы {len(rows)} точек"
        )
        outward = await r5_provider.build_duration_block(
            points, departure_time, rows, list(range(size))
        )
        for row_index, origin in enumerate(rows):
            durations[origin] = outward[row_index]
        if others:
            inward = await r5_provider.build_duration_block(points, departure_time, others, rows)
            for row_index, origin in enumerate(others):
                for column_index, destination in enumerate(rows):
                    durations[origin][destination] = inward[row_index][column_index]
    repaired = await r5_access.repair_duration_matrix(points, departure_time, durations)
    changed = [
        (i, j)
        for i in range(size)
        for j in range(size)
        if i != j and ((i, j) in missing or repaired[i][j] != known.get((i, j)))
    ]
    await travel_cache.save_matrix(points, departure_time, repaired, changed)
    return repaired


def covering_points(pairs: set[tuple[int, int]]) -> list[int]:
    """Как можно меньше точек, чтобы каждая пара начиналась или кончалась в одной из них.

    Обычно это новые точки — где бригада сейчас, новая заявка: жадно берём точку, на которую
    приходится больше всего непокрытых пар.
    """
    left = set(pairs)
    chosen: list[int] = []
    while left:
        load: dict[int, int] = defaultdict(int)
        for origin, destination in left:
            load[origin] += 1
            load[destination] += 1
        best = max(load, key=lambda index: (load[index], -index))
        chosen.append(best)
        left = {pair for pair in left if best not in pair}
    return sorted(chosen)


async def build_route(
    points: list[Point],
    transport: TransportKind,
    *,
    departure_time: datetime | None = None,
    leg_departure_times: list[datetime] | None = None,
    allow_fallback: bool = True,
) -> TravelRoute:
    if transport is TransportKind.PUBLIC_TRANSPORT:
        try:
            return await _r5_route(
                points,
                departure_time or clock.now().astimezone(local_timezone()),
                leg_departure_times=leg_departure_times,
            )
        except (httpx.HTTPError, KeyError, ValueError):
            if not allow_fallback:
                raise
            logger.warning(
                "R5 недоступен, использован приближённый маршрут общественного транспорта",
                exc_info=True,
            )
            return await _estimated_public_transport_route(points)

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

    return _route_of(legs, transport, provider)


async def _r5_route(
    points: list[Point],
    departure_time: datetime,
    *,
    leg_departure_times: list[datetime] | None,
) -> TravelRoute:
    if departure_time.tzinfo is None:
        raise ValueError("для маршрута R5 требуется время с часовым поясом")
    if leg_departure_times is not None:
        if len(leg_departure_times) != len(points) - 1:
            raise ValueError("число времён отправления не совпадает с числом плеч маршрута")
        if any(value.tzinfo is None for value in leg_departure_times):
            raise ValueError("время каждого отправления должно содержать часовой пояс")

    legs_of_route = list(pairwise(points))

    # одно и то же плечо с той же минутой выезда R5 считает одинаково — берём из кеша
    def ask(origin, destination, moment):
        return travel_cache.cached_route(origin, destination, moment, r5_access.route)

    if leg_departure_times is not None:
        # Времена выезда известны из плана — плечи не зависят друг от друга и считаются
        # разом. R5 ищет маршрут в один поток, зато держит несколько поисков сразу,
        # поэтому весь маршрут бригады обходится примерно во столько же, сколько одно плечо
        results = list(
            await asyncio.gather(
                *(
                    ask(origin, destination, leg_departure_times[index])
                    for index, (origin, destination) in enumerate(legs_of_route)
                )
            )
        )
    else:
        # Времени выезда нет: каждое следующее плечо начинается, когда закончилось
        # предыдущее, — считать наперёд нечего
        current_departure = departure_time
        results = []
        for origin, destination in legs_of_route:
            result = await ask(origin, destination, current_departure)
            results.append(result)
            current_departure += timedelta(minutes=result.total_duration_min)

    legs = [
        leg.model_copy(update={"visit_index": index})
        for index, result in enumerate(results)
        for leg in result.legs
    ]
    geometry = [leg.geometry for leg in legs]
    return TravelRoute(
        transport=TransportKind.PUBLIC_TRANSPORT,
        provider=(
            TravelProvider.VALHALLA
            if all(result.provider is TravelProvider.VALHALLA for result in results)
            else TravelProvider.R5
        ),
        distance_km=round(sum(leg.distance_km for leg in legs), 3),
        duration_min=round(sum(result.total_duration_min for result in results), 1),
        geometry=geometry if any(geometry) else [],
        legs=legs,
        walking_duration_min=round(sum(result.walking_duration_min for result in results), 1),
        waiting_duration_min=round(sum(result.waiting_duration_min for result in results), 1),
        transit_duration_min=round(sum(result.transit_duration_min for result in results), 1),
        entry_exit_penalty_min=round(sum(result.entry_exit_penalty_min for result in results), 1),
        reliability_buffer_min=round(sum(result.reliability_buffer_min for result in results), 1),
        transfers=sum(result.transfers for result in results),
    )


async def _estimated_public_transport_route(points: list[Point]) -> TravelRoute:
    try:
        legs = await valhalla_provider.route_legs(points, TransportKind.PUBLIC_TRANSPORT)
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning(
            "Valhalla недоступна, маршрут посчитан по haversine без геометрии",
            exc_info=True,
        )
        legs = haversine_provider.route_legs(points, TransportKind.PUBLIC_TRANSPORT)
    legs = transit_provider.legs_with_transit(points, legs, await _walking_legs(points))
    return _route_of(legs, TransportKind.PUBLIC_TRANSPORT, TravelProvider.TRANSIT_ESTIMATE)


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
