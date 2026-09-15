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
    # постоянные потери на визит: парковка у авто, ожидание и подход к остановке у ОТ
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
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def estimate(origin: Point, destination: Point, transport: TransportKind) -> TravelEstimate:
    profile = PROFILES[transport]
    distance_km = _straight_line_km(origin, destination) * profile.detour_factor
    if distance_km == 0.0:
        return TravelEstimate(distance_km=0.0, duration_min=0.0)
    duration_min = distance_km / profile.speed_kmh * 60 + profile.fixed_overhead_min
    return TravelEstimate(distance_km=round(distance_km, 3), duration_min=round(duration_min, 1))


def build_matrix(points: list[Point], transport: TransportKind) -> TravelMatrix:
    size = len(points)
    distances_km = [[0.0] * size for _ in range(size)]
    durations_min = [[0.0] * size for _ in range(size)]
    # обе половины считаются отдельно: у дорожного роутера матрица несимметрична (односторонние улицы)
    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            leg = estimate(points[i], points[j], transport)
            distances_km[i][j] = leg.distance_km
            durations_min[i][j] = leg.duration_min
    return TravelMatrix(
        transport=transport,
        provider=TravelProvider.HAVERSINE,
        points=points,
        distances_km=distances_km,
        durations_min=durations_min,
    )


def build_route(points: list[Point], transport: TransportKind) -> TravelRoute:
    legs = [estimate(points[i], points[i + 1], transport) for i in range(len(points) - 1)]
    return TravelRoute(
        transport=transport,
        provider=TravelProvider.HAVERSINE,
        distance_km=round(sum(leg.distance_km for leg in legs), 3),
        duration_min=round(sum(leg.duration_min for leg in legs), 1),
        geometry=[],
    )
