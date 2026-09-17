import enum

from pydantic import BaseModel, Field


class TransportKind(int, enum.Enum):
    """Зеркало справочника transport из db/init/002_seed.sql (значения фиксированы ТЗ)."""

    CAR = 1
    PEDESTRIAN = 2
    BICYCLE = 3
    PUBLIC_TRANSPORT = 4


class TravelProvider(str, enum.Enum):
    """Чем посчитаны цифры. Всегда возвращается наружу: haversine и Valhalla
    отличаются в разы, и подмена не должна проходить незаметно."""

    HAVERSINE = "haversine"
    VALHALLA = "valhalla"


class TravelMode(str, enum.Enum):
    """Чем человек преодолевает участок: важно для общественного транспорта."""

    ROAD = "road"
    METRO = "metro"
    WALK = "walk"


class Point(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class TravelEstimate(BaseModel):
    distance_km: float
    duration_min: float


class TravelRouteRequest(BaseModel):
    points: list[Point] = Field(min_length=2)
    transport: TransportKind = TransportKind.CAR


class TravelMatrixRequest(BaseModel):
    points: list[Point] = Field(min_length=2)
    transport: TransportKind = TransportKind.CAR


class TravelMatrix(BaseModel):
    transport: TransportKind
    provider: TravelProvider
    points: list[Point]
    distances_km: list[list[float | None]]
    durations_min: list[list[float | None]]


class TravelLeg(BaseModel):
    """Один переезд между соседними точками маршрута: из них собирается TravelRoute."""

    distance_km: float
    duration_min: float
    # encoded polyline участка; пусто, если геометрии нет (haversine)
    geometry: str = ""
    mode: TravelMode = TravelMode.ROAD


class TravelRoute(BaseModel):
    transport: TransportKind
    provider: TravelProvider
    distance_km: float
    duration_min: float
    # по одной encoded polyline на участок между соседними точками маршрута;
    # пусто у haversine — прямую линию фронт нарисует сам по координатам
    geometry: list[str]
    # те же участки подробно: сколько заняли и чем человек ехал
    legs: list[TravelLeg] = []
