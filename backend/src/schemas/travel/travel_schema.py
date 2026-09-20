import enum
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TransportKind(int, enum.Enum):
    """Зеркало справочника transport из db/init/002_seed.sql (значения фиксированы ТЗ)."""

    CAR = 1
    PEDESTRIAN = 2
    BICYCLE = 3
    PUBLIC_TRANSPORT = 4


class TravelProvider(str, enum.Enum):
    """Основной источник времени. Возвращается наружу, чтобы деградация была видна."""

    HAVERSINE = "haversine"
    VALHALLA = "valhalla"
    R5 = "r5"
    TRANSIT_ESTIMATE = "transit_estimate"


class TravelMode(str, enum.Enum):
    """Чем человек преодолевает участок: важно для общественного транспорта."""

    ROAD = "road"
    METRO = "metro"
    BUS = "bus"
    TRAM = "tram"
    RAIL = "rail"
    FERRY = "ferry"
    TRANSIT = "transit"
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
    departure_time: datetime | None = None

    @model_validator(mode="after")
    def validate_departure_time(self) -> "TravelRouteRequest":
        if self.departure_time is not None and self.departure_time.tzinfo is None:
            raise ValueError("departure_time должен содержать часовой пояс")
        return self


class TravelMatrixRequest(BaseModel):
    points: list[Point] = Field(min_length=2)
    transport: TransportKind = TransportKind.CAR
    departure_time: datetime | None = None

    @model_validator(mode="after")
    def validate_departure_time(self) -> "TravelMatrixRequest":
        if self.departure_time is not None and self.departure_time.tzinfo is None:
            raise ValueError("departure_time должен содержать часовой пояс")
        return self


class TravelMatrix(BaseModel):
    transport: TransportKind
    provider: TravelProvider
    points: list[Point]
    distances_km: list[list[float | None]]
    durations_min: list[list[float | None]]


class TravelLeg(BaseModel):
    """Один участок пути; R5 может вернуть несколько участков до одного визита."""

    distance_km: float
    duration_min: float
    # encoded polyline участка; пусто, если геометрии нет (haversine)
    geometry: str = ""
    mode: TravelMode = TravelMode.ROAD
    wait_min: float = 0
    route_id: str | None = None
    route_short_name: str | None = None  # н1, 205, МЦК из GTFS routes.txt
    route_color: str | None = None  # #RRGGBB из GTFS routes.txt
    from_stop_id: str | None = None
    to_stop_id: str | None = None
    visit_index: int | None = None  # номер следующей точки в points, начиная с нуля


class TravelRoute(BaseModel):
    transport: TransportKind
    provider: TravelProvider
    distance_km: float
    duration_min: float
    # по одной encoded polyline на участок между соседними точками маршрута;
    # пусто у haversine — прямую линию фронт нарисует сам по координатам
    geometry: list[str]
    # те же участки подробно: сколько заняли и чем человек ехал
    legs: list[TravelLeg] = Field(default_factory=list)
    walking_duration_min: float = 0
    waiting_duration_min: float = 0
    transit_duration_min: float = 0
    entry_exit_penalty_min: float = 0
    reliability_buffer_min: float = 0
    transfers: int = 0
