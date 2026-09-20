from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class MatrixPoint(Coordinate):
    id: str = Field(min_length=1, max_length=128, pattern=r".*\S.*")


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate
    departure_time: datetime

    @model_validator(mode="after")
    def validate_request(self) -> RouteRequest:
        if self.departure_time.tzinfo is None:
            raise ValueError("departure_time должен содержать часовой пояс")
        if self.origin == self.destination:
            raise ValueError("начальная и конечная точки должны различаться")
        return self


class MatrixRequest(BaseModel):
    points: list[MatrixPoint] = Field(min_length=2, max_length=1000)
    departure_time: datetime

    @model_validator(mode="after")
    def validate_request(self) -> MatrixRequest:
        if self.departure_time.tzinfo is None:
            raise ValueError("departure_time должен содержать часовой пояс")
        point_ids = [point.id for point in self.points]
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("идентификаторы точек матрицы должны быть уникальными")
        return self


class MatrixBlockRequest(BaseModel):
    origins: list[MatrixPoint] = Field(min_length=1, max_length=1000)
    destinations: list[MatrixPoint] = Field(min_length=1, max_length=1000)
    departure_time: datetime

    @model_validator(mode="after")
    def validate_request(self) -> MatrixBlockRequest:
        if self.departure_time.tzinfo is None:
            raise ValueError("departure_time должен содержать часовой пояс")
        for points in (self.origins, self.destinations):
            ids = [point.id for point in points]
            if len(ids) != len(set(ids)):
                raise ValueError("идентификаторы точек блока должны быть уникальными")
        return self


class RouteLeg(BaseModel):
    mode: str
    duration_seconds: int
    wait_seconds: int
    distance_meters: float | None
    route_id: str | None
    from_stop_id: str | None
    to_stop_id: str | None
    geometry: dict[str, Any] | None


class RouteResponse(BaseModel):
    departure_time: datetime
    raw_duration_seconds: int
    entry_exit_penalty_seconds: int
    reliability_buffer_seconds: int
    total_duration_seconds: int
    walking_duration_seconds: int
    waiting_duration_seconds: int
    transit_duration_seconds: int
    transfers: int
    legs: list[RouteLeg]


class MatrixResponse(BaseModel):
    departure_time: datetime
    departure_time_window_minutes: int
    reliability_buffer_ratio: float
    point_ids: list[str]
    raw_durations_seconds: list[list[int | None]]
    durations_seconds: list[list[int | None]]


class MatrixBlockResponse(BaseModel):
    departure_time: datetime
    departure_time_window_minutes: int
    reliability_buffer_ratio: float
    origin_ids: list[str]
    destination_ids: list[str]
    raw_durations_seconds: list[list[int | None]]
    durations_seconds: list[list[int | None]]


class HealthResponse(BaseModel):
    status: str
    network_loaded: bool
    error: str | None = None
