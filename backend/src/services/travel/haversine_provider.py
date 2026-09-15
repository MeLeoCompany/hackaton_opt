"""Запасной расчёт расстояния и времени в пути — без роутера, по прямой линии.

Используется, когда Valhalla недоступна. Цифры оценочные: расстояние по прямой
умножается на коэффициент извилистости улиц, время считается по средней скорости
транспорта плюс постоянные потери на каждый переезд.
"""

import math
from dataclasses import dataclass

from src.schemas.travel import (
    Point,
    TransportKind,
    TravelEstimate,
    TravelMatrix,
    TravelProvider,
    TravelRoute,
)

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class TransportProfile:
    speed_kmh: float
    # прямая линия короче реального пути по улицам; коэффициент приближает её к пробегу
    detour_factor: float
    # постоянные потери на каждый переезд: парковка у авто, ожидание и подход к остановке у ОТ
    fixed_overhead_min: float


PROFILES: dict[TransportKind, TransportProfile] = {
    TransportKind.CAR: TransportProfile(speed_kmh=30.0, detour_factor=1.30, fixed_overhead_min=5.0),
    TransportKind.PEDESTRIAN: TransportProfile(speed_kmh=5.0, detour_factor=1.15, fixed_overhead_min=0.0),
    TransportKind.BICYCLE: TransportProfile(speed_kmh=15.0, detour_factor=1.25, fixed_overhead_min=2.0),
    TransportKind.PUBLIC_TRANSPORT: TransportProfile(
        speed_kmh=18.0, detour_factor=1.35, fixed_overhead_min=10.0
    ),
}


def _straight_line_km(origin: Point, destination: Point) -> float:
    """Расстояние между двумя точками по поверхности Земли (формула гаверсинусов), км."""
    origin_latitude = math.radians(origin.latitude)
    destination_latitude = math.radians(destination.latitude)
    latitude_difference = destination_latitude - origin_latitude
    longitude_difference = math.radians(destination.longitude - origin.longitude)

    haversine = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(origin_latitude) * math.cos(destination_latitude) * math.sin(longitude_difference / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


def estimate(origin: Point, destination: Point, transport: TransportKind) -> TravelEstimate:
    """Оценка одного переезда: километры по улицам и минуты в пути для данного транспорта."""
    profile = PROFILES[transport]
    distance_km = _straight_line_km(origin, destination) * profile.detour_factor
    if distance_km == 0.0:
        return TravelEstimate(distance_km=0.0, duration_min=0.0)
    duration_min = distance_km / profile.speed_kmh * 60 + profile.fixed_overhead_min
    return TravelEstimate(distance_km=round(distance_km, 3), duration_min=round(duration_min, 1))


def build_matrix(points: list[Point], transport: TransportKind) -> TravelMatrix:
    """Матрица «из каждой точки в каждую»: километры и минуты для всех пар точек."""
    size = len(points)
    distances_km = [[0.0] * size for _ in range(size)]
    durations_min = [[0.0] * size for _ in range(size)]

    # «туда» и «обратно» считаются отдельно: у настоящего роутера они различаются
    # (односторонние улицы), и форма матрицы должна быть одинаковой у обоих провайдеров
    for from_index in range(size):
        for to_index in range(size):
            if from_index == to_index:
                continue
            trip = estimate(points[from_index], points[to_index], transport)
            distances_km[from_index][to_index] = trip.distance_km
            durations_min[from_index][to_index] = trip.duration_min

    return TravelMatrix(
        transport=transport,
        provider=TravelProvider.HAVERSINE,
        points=points,
        distances_km=distances_km,
        durations_min=durations_min,
    )


def build_route(points: list[Point], transport: TransportKind) -> TravelRoute:
    """Маршрут через точки по порядку: суммарные километры и минуты. Геометрии нет."""
    legs = [estimate(points[leg], points[leg + 1], transport) for leg in range(len(points) - 1)]
    return TravelRoute(
        transport=transport,
        provider=TravelProvider.HAVERSINE,
        distance_km=round(sum(leg.distance_km for leg in legs), 3),
        duration_min=round(sum(leg.duration_min for leg in legs), 1),
        geometry=[],
    )
