"""Кеш ответов R5 в базе (docs/algoCachV1.md).

Ответ R5 зависит только от точек и времени выезда, а расписание считаем одинаковым каждый
день — поэтому ключ: координаты отправления и назначения плюс время суток выезда (секунды от
полуночи по Москве). Два вида записей:
  - matrix — пара матрицы (минуты R5 после досчёта изолированных точек), для cuOpt;
  - route  — поездка по одному плечу (/route со всеми пешими подходами), для проверки
    расписания и маршрутов на карте.
Матрица берёт только matrix, проверка — только route: числа в расчёте такие же, как без кеша.

Кеш — ускорение, а не источник правды: не ответила база — считаем через R5, как раньше.
Каждое обращение идёт своей короткой транзакцией, отдельно от расчёта: пробный пересчёт
откатывает свою транзакцию, а посчитанное им в кеше остаётся.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from src.core.config import settings
from src.core.local_day import local_timezone
from src.db.session import async_session_maker
from src.models import SolverMemory, TravelCache, TravelCacheState
from src.schemas.travel import Point, TravelLeg, TravelProvider
from src.services.travel.r5_provider import RouteResult

logger = logging.getLogger(__name__)

MATRIX = "matrix"
ROUTE = "route"
# сколько строк пишем одним запросом: у Postgres предел параметров на запрос
SAVE_CHUNK = 1000
# как часто чистим старые записи и сверяем расписание
MAINTENANCE_SECONDS = 24 * 60 * 60

PointKey = tuple[Decimal, Decimal]


def point_key(point: Point) -> PointKey:
    """Координаты до шестого знака — как они лежат в базе (numeric(10, 6))."""
    return (
        Decimal(str(round(float(point.latitude), 6))),
        Decimal(str(round(float(point.longitude), 6))),
    )


def depart_seconds(moment: datetime) -> int:
    """Время суток выезда по Москве в секундах: дата в ключ не входит."""
    local = moment.astimezone(local_timezone())
    return local.hour * 3600 + local.minute * 60 + local.second


# ---- счётчики для журнала: сколько плеч взято из кеша, сколько спрошено у R5 ----


@dataclass
class RouteCounters:
    from_cache: int = 0
    from_r5: int = 0


_counters: ContextVar[RouteCounters | None] = ContextVar("travel_cache_counters", default=None)


@contextmanager
def counting():
    """Считать обращения за плечами внутри блока: проверка расписания, маршруты для карты."""
    counters = RouteCounters()
    token = _counters.set(counters)
    try:
        yield counters
    finally:
        _counters.reset(token)


def _count(from_cache: bool) -> None:
    counters = _counters.get()
    if counters is None:
        return
    if from_cache:
        counters.from_cache += 1
    else:
        counters.from_r5 += 1


# ---- матрица ----


async def load_matrix(
    points: list[Point], departure: datetime
) -> dict[tuple[int, int], float | None]:
    """Известные пары матрицы по индексам точек; диагональ не хранится.

    Значение None — R5 пути не нашёл (это тоже ответ, его не спрашиваем заново).
    """
    if not settings.travel_cache_enabled or len(points) < 2:
        return {}
    keys = [point_key(point) for point in points]
    unique = sorted(set(keys))
    try:
        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(
                        TravelCache.from_lat,
                        TravelCache.from_lon,
                        TravelCache.to_lat,
                        TravelCache.to_lon,
                        TravelCache.duration_min,
                    ).where(
                        TravelCache.kind == MATRIX,
                        TravelCache.depart_seconds == depart_seconds(departure),
                        tuple_(TravelCache.from_lat, TravelCache.from_lon).in_(unique),
                        tuple_(TravelCache.to_lat, TravelCache.to_lon).in_(unique),
                    )
                )
            ).all()
    except Exception:
        logger.warning("Кеш R5 недоступен — матрица считается целиком", exc_info=True)
        return {}
    stored = {((row[0], row[1]), (row[2], row[3])): row[4] for row in rows}
    known = {}
    for origin_index, origin in enumerate(keys):
        for destination_index, destination in enumerate(keys):
            if origin_index == destination_index:
                continue
            if (origin, destination) in stored:
                known[origin_index, destination_index] = stored[origin, destination]
    return known


async def save_matrix(
    points: list[Point],
    departure: datetime,
    durations: list[list[float | None]],
    pairs: Iterable[tuple[int, int]],
) -> None:
    """Запомнить пары матрицы (по индексам точек); уже известные перезаписываются."""
    if not settings.travel_cache_enabled:
        return
    keys = [point_key(point) for point in points]
    seconds = depart_seconds(departure)
    values = {}
    for origin_index, destination_index in pairs:
        if origin_index == destination_index:
            continue
        origin, destination = keys[origin_index], keys[destination_index]
        values[origin, destination] = durations[origin_index][destination_index]
    await _upsert(
        [
            {
                "kind": MATRIX,
                "depart_seconds": seconds,
                "from_lat": origin[0],
                "from_lon": origin[1],
                "to_lat": destination[0],
                "to_lon": destination[1],
                "duration_min": duration,
                "route": None,
            }
            for (origin, destination), duration in values.items()
        ]
    )


# ---- плечи маршрутов ----


def route_to_json(result: RouteResult) -> dict:
    return {
        "legs": [leg.model_dump(mode="json") for leg in result.legs],
        "total_duration_min": result.total_duration_min,
        "walking_duration_min": result.walking_duration_min,
        "waiting_duration_min": result.waiting_duration_min,
        "transit_duration_min": result.transit_duration_min,
        "entry_exit_penalty_min": result.entry_exit_penalty_min,
        "reliability_buffer_min": result.reliability_buffer_min,
        "transfers": result.transfers,
        "provider": result.provider.value,
    }


def route_from_json(data: dict) -> RouteResult:
    return RouteResult(
        legs=[TravelLeg.model_validate(leg) for leg in data["legs"]],
        total_duration_min=data["total_duration_min"],
        walking_duration_min=data["walking_duration_min"],
        waiting_duration_min=data["waiting_duration_min"],
        transit_duration_min=data["transit_duration_min"],
        entry_exit_penalty_min=data["entry_exit_penalty_min"],
        reliability_buffer_min=data["reliability_buffer_min"],
        transfers=data["transfers"],
        provider=TravelProvider(data["provider"]),
    )


async def cached_route(
    origin: Point,
    destination: Point,
    departure: datetime,
    build: Callable[[Point, Point, datetime], Awaitable[RouteResult]],
) -> RouteResult:
    """Поездка по плечу: из кеша, иначе build (R5) — и запомнить."""
    if not settings.travel_cache_enabled:
        _count(from_cache=False)
        return await build(origin, destination, departure)
    origin_key, destination_key = point_key(origin), point_key(destination)
    seconds = depart_seconds(departure)
    try:
        async with async_session_maker() as session:
            stored = await session.scalar(
                select(TravelCache.route).where(
                    TravelCache.kind == ROUTE,
                    TravelCache.depart_seconds == seconds,
                    TravelCache.from_lat == origin_key[0],
                    TravelCache.from_lon == origin_key[1],
                    TravelCache.to_lat == destination_key[0],
                    TravelCache.to_lon == destination_key[1],
                )
            )
    except Exception:
        logger.warning("Кеш R5 недоступен — плечо считается заново", exc_info=True)
        stored = None
    if stored is not None:
        try:
            result = route_from_json(stored)
        except (KeyError, TypeError, ValueError):
            logger.warning("Запись кеша R5 не читается — плечо считается заново", exc_info=True)
        else:
            _count(from_cache=True)
            return result

    result = await build(origin, destination, departure)
    _count(from_cache=False)
    await _upsert(
        [
            {
                "kind": ROUTE,
                "depart_seconds": seconds,
                "from_lat": origin_key[0],
                "from_lon": origin_key[1],
                "to_lat": destination_key[0],
                "to_lon": destination_key[1],
                "duration_min": result.total_duration_min,
                "route": route_to_json(result),
            }
        ]
    )
    return result


async def _upsert(rows: list[dict]) -> None:
    if not rows:
        return
    try:
        async with async_session_maker() as session:
            for start in range(0, len(rows), SAVE_CHUNK):
                statement = insert(TravelCache).values(rows[start : start + SAVE_CHUNK])
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            TravelCache.kind,
                            TravelCache.depart_seconds,
                            TravelCache.from_lat,
                            TravelCache.from_lon,
                            TravelCache.to_lat,
                            TravelCache.to_lon,
                        ],
                        set_={
                            "duration_min": statement.excluded.duration_min,
                            "route": statement.excluded.route,
                            "created_at": func.now(),
                        },
                    )
                )
            await session.commit()
    except Exception:
        # не записали — в следующий раз посчитаем заново; расчёт от этого не страдает
        logger.warning("Кеш R5: не удалось сохранить ответы", exc_info=True)


# ---- обслуживание: срок хранения, смена расписания, сброс из настроек ----


@dataclass(frozen=True)
class CacheStats:
    matrix_pairs: int
    routes: int
    # решения cuOpt по отпечатку задачи (solver_memory) — живут и чистятся вместе с кешем R5
    solutions: int
    oldest_at: datetime | None
    keep_days: int


async def stats() -> CacheStats:
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(TravelCache.kind, func.count(), func.min(TravelCache.created_at)).group_by(
                    TravelCache.kind
                )
            )
        ).all()
        solutions, oldest_solution = (
            await session.execute(select(func.count(), func.min(SolverMemory.created_at)))
        ).one()
    counts = {kind: count for kind, count, _ in rows}
    oldest = [created for _, _, created in rows if created is not None]
    if oldest_solution is not None:
        oldest.append(oldest_solution)
    return CacheStats(
        matrix_pairs=counts.get(MATRIX, 0),
        routes=counts.get(ROUTE, 0),
        solutions=solutions,
        oldest_at=min(oldest) if oldest else None,
        keep_days=settings.travel_cache_days,
    )


async def clear() -> int:
    """Сбросить весь кеш — кнопкой в «Системе» или при смене расписания.

    Решения cuOpt сбрасываются вместе с ним: они посчитаны по матрицам из этого кеша.
    """
    async with async_session_maker() as session:
        deleted = (await session.execute(delete(TravelCache))).rowcount or 0
        deleted += (await session.execute(delete(SolverMemory))).rowcount or 0
        await session.execute(
            update(TravelCacheState).where(TravelCacheState.id == 1).values(cleaned_at=func.now())
        )
        await session.commit()
    logger.info("Кеш R5 сброшен: удалено записей %s", deleted)
    return deleted


async def remove_expired() -> int:
    """Удалить ответы старше travel_cache_days дней — по настоящему времени, не по демо-часам."""
    async with async_session_maker() as session:
        deleted = (
            await session.execute(
                delete(TravelCache).where(
                    TravelCache.created_at < func.now() - timedelta(days=settings.travel_cache_days)
                )
            )
        ).rowcount or 0
        await session.execute(
            update(TravelCacheState).where(TravelCacheState.id == 1).values(cleaned_at=func.now())
        )
        await session.commit()
    if deleted:
        logger.info("Кеш R5: удалено устаревших записей %s", deleted)
    return deleted


def gtfs_fingerprint() -> str | None:
    """Отпечаток файла расписания: размер и время изменения. Нет файла — None."""
    try:
        info = settings.r5_gtfs_path.stat()
    except OSError:
        return None
    return f"{info.st_size}:{info.st_mtime_ns}"


async def clear_if_schedule_changed() -> bool:
    """Расписание GTFS сменилось — старые ответы R5 неверны, кеш очищается целиком."""
    current = gtfs_fingerprint()
    if current is None:
        return False
    async with async_session_maker() as session:
        stored = await session.scalar(
            select(TravelCacheState.gtfs_fingerprint).where(TravelCacheState.id == 1)
        )
    if stored == current:
        return False
    if stored is not None:
        logger.info("Расписание GTFS сменилось — сбрасываю кеш R5")
        await clear()
    async with async_session_maker() as session:
        await session.execute(
            update(TravelCacheState)
            .where(TravelCacheState.id == 1)
            .values(gtfs_fingerprint=current)
        )
        await session.commit()
    return stored is not None


async def maintenance_loop() -> None:
    """Раз в сутки: сверить расписание и удалить старое. Ошибки не роняют приложение."""
    if not settings.travel_cache_enabled:
        return
    while True:
        try:
            await clear_if_schedule_changed()
            await remove_expired()
        except Exception:
            logger.warning("Кеш R5: обслуживание не удалось, повторю позже", exc_info=True)
        await asyncio.sleep(MAINTENANCE_SECONDS)
