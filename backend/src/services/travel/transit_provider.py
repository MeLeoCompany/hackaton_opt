"""Как на самом деле едет исполнитель без машины: метро, пешком или наземным транспортом.

Метро — регулярный транспорт: расписания нет, но поезда ходят часто.

Наземный транспорт Valhalla считает по дорогам (костинг bus), а метро в дорожном графе нет
вовсе — поэтому поездка через весь город на общественном транспорте выходила втрое длиннее
настоящей. Здесь метро добавляется отдельной моделью, без расписания:

  пешком до ближайшей станции -> ожидание поезда -> перегоны по схеме линий -> пересадки
  -> пешком от станции до точки.

Интервалы в московском метро 1–6 минут, поэтому вместо расписания берётся половина типичного
интервала (WAIT_MIN), а время перегона считается по коммерческой скорости с остановками.
Схема линий — metro_moscow.json из OpenStreetMap (обновляется scripts/fetch_metro.py).

Короткие перегоны человек проходит пешком, а не ждёт транспорт, поэтому пеший вариант
сравнивается наравне с метро. Пеший вариант приходит снаружи, посчитанный Valhalla по
пешеходному графу: иначе через реку или пути «по прямой» получалось бы 400 метров там, где
идти два километра до моста. Если пешеходный расчёт не вышел, берётся прямая линия.

Наружу модуль даёт две вещи: matrix_with_transit (матрица дня) и legs_with_transit (участки
готового маршрута). В обоих случаях метро или пеший вариант берутся только там, где они
быстрее наземного.
"""

import heapq
import json
import math
import pathlib
from dataclasses import dataclass

from src.schemas.travel import Point, TransportKind, TravelLeg, TravelMatrix, TravelMode
from src.services.travel.polyline import encode

EARTH_RADIUS_KM = 6371.0088

# пешие подходы: скорость в городе с переходами и коэффициент от прямой линии к улицам
WALK_SPEED_KMH = 4.5
WALK_DETOUR = 1.25
# дальше пешком до метро не идут — поедут наземным
ACCESS_KM = 1.2
# сколько ближайших станций рассматривать как вход/выход
ACCESS_STATIONS = 5

# дальше этого расстояния пешком не ходят, едут
WALK_INSTEAD_KM = 2.5

# коммерческая скорость московского метро с остановками; тоннель длиннее прямой линии
TRAIN_SPEED_KMH = 40.0
TRACK_DETOUR = 1.08
# интервал 2–6 минут, ждать в среднем половину; расписание для этого не нужно
WAIT_MIN = 3.0
# переход между станциями узла: пешком по переходу плюс ожидание следующего поезда
TRANSFER_MIN = 4.0
TRANSFER_KM = 0.5

SCHEME_PATH = pathlib.Path(__file__).with_name("metro_moscow.json")


@dataclass(frozen=True)
class TransitTrip:
    duration_min: float
    distance_km: float
    # промежуточные точки для линии на карте: станции входа, пересадок и выхода.
    # у пешего варианта их нет — линия идёт напрямую
    stations: list[Point]


def _straight_line_km(origin: Point, destination: Point) -> float:
    """Расстояние между двумя точками по поверхности Земли (формула гаверсинусов), км."""
    origin_latitude = math.radians(origin.latitude)
    destination_latitude = math.radians(destination.latitude)
    latitude_difference = destination_latitude - origin_latitude
    longitude_difference = math.radians(destination.longitude - origin.longitude)

    haversine = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(origin_latitude)
        * math.cos(destination_latitude)
        * math.sin(longitude_difference / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


def _load_scheme() -> tuple[list[Point], list[list[tuple[int, float, float]]]]:
    """Схема из JSON -> точки станций и связи между ними (сосед, минуты, километры).

    Связи двух видов: перегон по линии и пересадка между станциями разных линий,
    стоящими рядом (в Москве это и одноимённые станции, и узлы вроде Театральной).
    """
    scheme = json.loads(SCHEME_PATH.read_text(encoding="utf-8"))
    stations = [
        Point(latitude=station["lat"], longitude=station["lon"]) for station in scheme["stations"]
    ]
    lines = [station["line"] for station in scheme["stations"]]
    links: list[list[tuple[int, float, float]]] = [[] for _ in stations]

    for line in scheme["lines"]:
        order = line["stations"]
        for position in range(len(order) - 1):
            first, second = order[position], order[position + 1]
            ride_km = _straight_line_km(stations[first], stations[second]) * TRACK_DETOUR
            ride_min = ride_km / TRAIN_SPEED_KMH * 60
            links[first].append((second, ride_min, ride_km))
            links[second].append((first, ride_min, ride_km))

    for first in range(len(stations)):
        for second in range(first + 1, len(stations)):
            if lines[first] == lines[second]:
                continue
            walk_km = _straight_line_km(stations[first], stations[second])
            if walk_km > TRANSFER_KM:
                continue
            links[first].append((second, TRANSFER_MIN, walk_km))
            links[second].append((first, TRANSFER_MIN, walk_km))

    return stations, links


STATIONS, LINKS = _load_scheme()


def _walk_leg(walking: TravelMatrix | None, row: int, column: int) -> TravelLeg | None:
    """Пеший переезд из матрицы пешеходных расчётов; None — если её нет или пути нет."""
    if walking is None:
        return None
    minutes = walking.durations_min[row][column]
    kilometres = walking.distances_km[row][column]
    if minutes is None or kilometres is None:
        return None
    return TravelLeg(distance_km=kilometres, duration_min=minutes)


def _access(point: Point) -> list[tuple[int, float, float]]:
    """Станции в пешей доступности от точки: (станция, минуты пешком, километры)."""
    nearby = []
    for index, station in enumerate(STATIONS):
        walk_km = _straight_line_km(point, station) * WALK_DETOUR
        if walk_km <= ACCESS_KM:
            nearby.append((index, walk_km / WALK_SPEED_KMH * 60, walk_km))
    nearby.sort(key=lambda entry: entry[1])
    return nearby[:ACCESS_STATIONS]


def _reach(origin: Point) -> tuple[list[float], list[float], list[int]]:
    """Дейкстра от точки по схеме метро: минуты и километры до каждой станции.

    Третий список — откуда пришли, по нему восстанавливается цепочка станций для карты.
    """
    minutes = [math.inf] * len(STATIONS)
    kilometres = [0.0] * len(STATIONS)
    came_from = [-1] * len(STATIONS)
    queue: list[tuple[float, int]] = []

    for index, walk_min, walk_km in _access(origin):
        # ожидание поезда — один раз при входе в метро, дальше только пересадки
        minutes[index] = walk_min + WAIT_MIN
        kilometres[index] = walk_km
        heapq.heappush(queue, (minutes[index], index))

    while queue:
        reached_min, station = heapq.heappop(queue)
        if reached_min > minutes[station]:
            continue
        for neighbour, link_min, link_km in LINKS[station]:
            candidate = reached_min + link_min
            if candidate >= minutes[neighbour]:
                continue
            minutes[neighbour] = candidate
            kilometres[neighbour] = kilometres[station] + link_km
            came_from[neighbour] = station
            heapq.heappush(queue, (candidate, neighbour))

    return minutes, kilometres, came_from


def _finish(
    reached: tuple[list[float], list[float], list[int]], destination: Point
) -> TransitTrip | None:
    """Лучшая станция выхода для точки назначения и вся поездка целиком."""
    minutes, kilometres, came_from = reached
    best: TransitTrip | None = None
    for index, walk_min, walk_km in _access(destination):
        if math.isinf(minutes[index]):
            continue
        duration = minutes[index] + walk_min
        if best is not None and duration >= best.duration_min:
            continue
        chain: list[int] = []
        station = index
        while station != -1:
            chain.append(station)
            station = came_from[station]
        chain.reverse()
        best = TransitTrip(
            duration_min=round(duration, 1),
            distance_km=round(kilometres[index] + walk_km, 3),
            stations=[STATIONS[station] for station in chain],
        )
    return best


def _straight_walk(origin: Point, destination: Point) -> TransitTrip | None:
    """Пеший вариант по прямой линии — запасной, когда пешеходного расчёта нет."""
    walk_km = _straight_line_km(origin, destination) * WALK_DETOUR
    if walk_km > WALK_INSTEAD_KM:
        return None
    return TransitTrip(
        duration_min=round(walk_km / WALK_SPEED_KMH * 60, 1),
        distance_km=round(walk_km, 3),
        stations=[],
    )


def _walk_trip(origin: Point, destination: Point, walk: TravelLeg | None) -> TransitTrip | None:
    """Пеший вариант перегона; None — если идти слишком далеко или негде."""
    if walk is None:
        return _straight_walk(origin, destination)
    if walk.distance_km > WALK_INSTEAD_KM:
        return None
    return TransitTrip(duration_min=walk.duration_min, distance_km=walk.distance_km, stations=[])


def _best_trip(
    reached: tuple[list[float], list[float], list[int]],
    origin: Point,
    destination: Point,
    walk: TravelLeg | None = None,
) -> TransitTrip | None:
    """Лучший из вариантов «метро» и «пешком» для одного перегона."""
    found = [
        option
        for option in (_finish(reached, destination), _walk_trip(origin, destination, walk))
        if option is not None
    ]
    return min(found, key=lambda trip: trip.duration_min) if found else None


def fastest_trip(
    origin: Point, destination: Point, walk: TravelLeg | None = None
) -> TransitTrip | None:
    """Быстрейший вариант без машины между двумя точками: метро или пешком."""
    return _best_trip(_reach(origin), origin, destination, walk)


def matrix_with_transit(matrix: TravelMatrix, walking: TravelMatrix | None = None) -> TravelMatrix:
    """Матрица наземного транспорта -> та же матрица, где метро или пеший путь быстрее.

    walking — матрица пешком от Valhalla (может не быть, тогда пешие куски идут по прямой).
    Дейкстра считается один раз на строку матрицы, а не на каждую пару.
    """
    if matrix.transport is not TransportKind.PUBLIC_TRANSPORT:
        return matrix

    durations = [list(row) for row in matrix.durations_min]
    distances = [list(row) for row in matrix.distances_km]
    for from_index, origin in enumerate(matrix.points):
        reached = _reach(origin)
        for to_index, destination in enumerate(matrix.points):
            if from_index == to_index:
                continue
            trip = _best_trip(
                reached, origin, destination, _walk_leg(walking, from_index, to_index)
            )
            if trip is None:
                continue
            surface = durations[from_index][to_index]
            # None у наземного — дороги нет вовсе, тогда метро тем более выигрывает
            if surface is not None and surface <= trip.duration_min:
                continue
            durations[from_index][to_index] = trip.duration_min
            distances[from_index][to_index] = trip.distance_km

    return matrix.model_copy(update={"durations_min": durations, "distances_km": distances})


def legs_with_transit(
    points: list[Point], legs: list[TravelLeg], walking: list[TravelLeg] | None = None
) -> list[TravelLeg]:
    """Участки маршрута -> те же участки, где метро или пеший путь быстрее наземного.

    У заменённого участка своя линия для карты: прямые отрезки через станции (а у пешего
    варианта — напрямую), а не дорога.
    """
    updated = []
    for index, leg in enumerate(legs):
        origin, destination = points[index], points[index + 1]
        walk = walking[index] if walking is not None and index < len(walking) else None
        trip = fastest_trip(origin, destination, walk)
        if trip is None or trip.duration_min >= leg.duration_min:
            updated.append(leg)
            continue
        if walk is not None and not trip.stations:
            # пешком: линия уже посчитана Valhalla по тротуарам
            updated.append(walk.model_copy(update={"mode": TravelMode.WALK}))
            continue
        updated.append(
            TravelLeg(
                distance_km=trip.distance_km,
                duration_min=trip.duration_min,
                geometry=encode([origin, *trip.stations, destination]),
                mode=TravelMode.METRO if trip.stations else TravelMode.WALK,
            )
        )
    return updated
