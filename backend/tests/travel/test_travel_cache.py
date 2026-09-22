"""Кеш ответов R5 (docs/algoCachV1.md): с кешем матрица и маршруты те же, что без него.

База и R5 здесь подменены: «R5» — детерминированная функция от пары точек, «кеш» — словарь.
Главная проверка — при любом наборе уже известных пар собранная матрица совпадает с полной,
а R5 спрашивают только о недостающих.
"""

import random
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.travel import Point, TravelLeg, TravelMode, TravelProvider
from src.services.planner.planner_loader import floor_to_minutes
from src.services.travel import r5_provider, travel_cache, travel_service
from src.services.travel.travel_service import covering_points

DEPARTURE = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)


def points_of(count):
    return [Point(latitude=55.7 + index * 0.001, longitude=37.6) for index in range(count)]


def fake_minutes(origin: Point, destination: Point) -> float | None:
    """«R5»: у каждой пары своё время; к части пар пути нет."""
    if origin == destination:
        return 0.0
    code = round(origin.latitude * 1e6) * 7 + round(destination.latitude * 1e6) * 3
    return None if code % 11 == 0 else (code % 97) / 3


class FakeR5:
    def __init__(self):
        self.full_calls = 0
        self.block_pairs = 0

    async def full(self, points, departure):
        self.full_calls += 1
        return [[fake_minutes(a, b) for b in points] for a in points]

    async def block(self, points, departure, origins, destinations):
        self.block_pairs += len(origins) * len(destinations)
        return [[fake_minutes(points[i], points[j]) for j in destinations] for i in origins]


class FakeCache:
    """Кеш матрицы в памяти с тем же ключом, что в базе: координаты и время суток."""

    def __init__(self):
        self.rows = {}

    def key(self, origin, destination, departure):
        return (
            travel_cache.point_key(origin),
            travel_cache.point_key(destination),
            travel_cache.depart_seconds(departure),
        )

    async def load(self, points, departure):
        return {
            (i, j): self.rows[self.key(a, b, departure)]
            for i, a in enumerate(points)
            for j, b in enumerate(points)
            if i != j and self.key(a, b, departure) in self.rows
        }

    async def save(self, points, departure, durations, pairs):
        for i, j in pairs:
            if i != j:
                self.rows[self.key(points[i], points[j], departure)] = durations[i][j]


async def no_repair(points, departure, durations):
    return [row.copy() for row in durations]


async def r5_matrix(points, r5, cache):
    with (
        patch.object(r5_provider, "build_duration_matrix", r5.full),
        patch.object(r5_provider, "build_duration_block", r5.block),
        patch.object(travel_service.r5_access, "repair_duration_matrix", no_repair),
        patch.object(travel_cache, "load_matrix", cache.load),
        patch.object(travel_cache, "save_matrix", cache.save),
    ):
        return await travel_service._r5_durations(points, DEPARTURE)


def expected(points):
    return [[fake_minutes(a, b) for b in points] for a in points]


@pytest.mark.asyncio
async def test_first_matrix_is_full_and_goes_to_cache():
    points = points_of(6)
    r5, cache = FakeR5(), FakeCache()

    durations = await r5_matrix(points, r5, cache)

    assert durations == expected(points)
    assert r5.full_calls == 1 and r5.block_pairs == 0
    assert len(cache.rows) == 6 * 5  # диагональ не хранится


@pytest.mark.asyncio
async def test_same_points_come_from_cache_without_r5():
    points = points_of(6)
    cache = FakeCache()
    await r5_matrix(points, FakeR5(), cache)
    r5 = FakeR5()

    durations = await r5_matrix(points, r5, cache)

    assert durations == expected(points)
    assert (r5.full_calls, r5.block_pairs) == (0, 0)


@pytest.mark.asyncio
async def test_new_point_costs_only_its_row_and_column():
    """Пересчёт: бригада сдвинулась — появилась одна новая точка."""
    points = points_of(6)
    cache = FakeCache()
    await r5_matrix(points, FakeR5(), cache)
    moved = [*points[:2], Point(latitude=55.8, longitude=37.7), *points[2:]]
    r5 = FakeR5()

    durations = await r5_matrix(moved, r5, cache)

    assert durations == expected(moved)
    assert r5.full_calls == 0
    # строка новой точки на все 7 и столбец — от остальных 6
    assert r5.block_pairs == 7 + 6


@pytest.mark.asyncio
async def test_dropped_points_do_not_need_r5():
    """Утверждение: перенесённые и отменённые заявки просто выпадают."""
    points = points_of(8)
    cache = FakeCache()
    await r5_matrix(points, FakeR5(), cache)
    r5 = FakeR5()

    remaining = [points[0], points[2], points[5], points[7]]
    durations = await r5_matrix(remaining, r5, cache)

    assert durations == expected(remaining)
    assert (r5.full_calls, r5.block_pairs) == (0, 0)


@pytest.mark.asyncio
async def test_any_known_subset_gives_the_same_matrix():
    """Сколько бы и каких пар ни лежало в кеше — матрица та же, что посчитанная целиком."""
    rng = random.Random(7)
    for _ in range(40):
        points = points_of(rng.randint(2, 12))
        cache = FakeCache()
        for i, a in enumerate(points):
            for j, b in enumerate(points):
                if i != j and rng.random() < 0.6:
                    cache.rows[cache.key(a, b, DEPARTURE)] = fake_minutes(a, b)
        r5 = FakeR5()

        durations = await r5_matrix(points, r5, cache)

        assert durations == expected(points)
        # после расчёта в кеше все пары
        assert all(
            cache.key(a, b, DEPARTURE) in cache.rows
            for i, a in enumerate(points)
            for j, b in enumerate(points)
            if i != j
        )


@pytest.mark.asyncio
async def test_same_address_pairs_are_kept_as_r5_counted_them():
    """Две заявки по одному адресу: пара между ними — не диагональ, берём то, что дал R5."""
    points = [*points_of(3), points_of(3)[1]]
    cache = FakeCache()
    await r5_matrix(points, FakeR5(), cache)

    durations = await r5_matrix(points, FakeR5(), cache)

    assert durations == expected(points)
    assert durations[1][3] == fake_minutes(points[1], points[3])


@pytest.mark.asyncio
async def test_other_time_of_day_is_another_matrix():
    points = points_of(4)
    cache = FakeCache()
    await r5_matrix(points, FakeR5(), cache)
    r5 = FakeR5()

    with (
        patch.object(r5_provider, "build_duration_matrix", r5.full),
        patch.object(r5_provider, "build_duration_block", r5.block),
        patch.object(travel_service.r5_access, "repair_duration_matrix", no_repair),
        patch.object(travel_cache, "load_matrix", cache.load),
        patch.object(travel_cache, "save_matrix", cache.save),
    ):
        await travel_service._r5_durations(points, DEPARTURE + timedelta(minutes=10))

    assert r5.full_calls == 1


@pytest.mark.asyncio
async def test_other_day_same_time_is_the_same_record():
    """Расписание считаем одинаковым каждый день: дата в ключ не входит."""
    assert travel_cache.depart_seconds(DEPARTURE) == travel_cache.depart_seconds(
        DEPARTURE + timedelta(days=3)
    )
    msk = timezone(timedelta(hours=3))
    assert travel_cache.depart_seconds(datetime(2026, 8, 17, 12, 0, tzinfo=msk)) == 12 * 3600


@pytest.mark.asyncio
async def test_repaired_pairs_are_saved_too():
    """Изолированную точку досчитывает r5_access; досчитанное тоже ложится в кеш."""
    points = points_of(3)
    r5, cache = FakeR5(), FakeCache()

    async def repair(points, departure, durations):
        repaired = [row.copy() for row in durations]
        repaired[0][2] = 42.0
        return repaired

    with (
        patch.object(r5_provider, "build_duration_matrix", r5.full),
        patch.object(travel_service.r5_access, "repair_duration_matrix", repair),
        patch.object(travel_cache, "load_matrix", cache.load),
        patch.object(travel_cache, "save_matrix", cache.save),
    ):
        await travel_service._r5_durations(points, DEPARTURE)

    assert cache.rows[cache.key(points[0], points[2], DEPARTURE)] == 42.0


def test_covering_points_prefers_the_new_point():
    size = 6
    new = 4
    pairs = {(new, j) for j in range(size) if j != new} | {
        (i, new) for i in range(size) if i != new
    }

    assert covering_points(pairs) == [new]


def test_covering_points_covers_every_pair():
    rng = random.Random(3)
    for _ in range(50):
        pairs = {(rng.randrange(9), rng.randrange(9)) for _ in range(rng.randint(1, 30))}
        pairs = {pair for pair in pairs if pair[0] != pair[1]}
        chosen = set(covering_points(pairs))
        assert all(origin in chosen or destination in chosen for origin, destination in pairs)


def test_route_survives_the_round_trip_exactly():
    result = r5_provider.RouteResult(
        legs=[
            TravelLeg(distance_km=0.412, duration_min=5.3, geometry="abc", mode=TravelMode.WALK),
            TravelLeg(
                distance_km=7.1,
                duration_min=21.7,
                wait_min=3.2,
                geometry="def",
                mode=TravelMode.BUS,
                route_id="bus-12",
                route_short_name="12",
                route_color="#FF0000",
                from_stop_id="s1",
                to_stop_id="s2",
            ),
        ],
        total_duration_min=27.016666666666666,
        walking_duration_min=5.3,
        waiting_duration_min=3.2,
        transit_duration_min=18.5,
        entry_exit_penalty_min=0.0,
        reliability_buffer_min=1.8,
        transfers=0,
        provider=TravelProvider.R5,
    )

    assert travel_cache.route_from_json(travel_cache.route_to_json(result)) == result


@pytest.mark.asyncio
async def test_without_cache_every_leg_goes_to_r5_and_is_counted():
    build = AsyncMock(return_value="маршрут")
    origin, destination = points_of(2)

    with travel_cache.counting() as counters:
        first = await travel_cache.cached_route(origin, destination, DEPARTURE, build)
        await travel_cache.cached_route(origin, destination, DEPARTURE, build)

    assert first == "маршрут"
    assert build.await_count == 2
    assert (counters.from_cache, counters.from_r5) == (0, 2)


def test_replan_departure_is_rounded_down_to_ten_minutes():
    moment = datetime(2026, 8, 17, 14, 43, 20, 5, tzinfo=UTC)

    assert floor_to_minutes(moment, 10) == datetime(2026, 8, 17, 14, 40, tzinfo=UTC)
    assert floor_to_minutes(datetime(2026, 8, 17, 9, 0, tzinfo=UTC), 10).minute == 0
