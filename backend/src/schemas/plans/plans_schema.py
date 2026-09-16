from datetime import date, datetime

from pydantic import BaseModel


class PlanBuildRequest(BaseModel):
    plan_date: date


class PlanningDayOption(BaseModel):
    """День, на который есть активные заявки."""

    plan_date: date
    active_requests: int


class PlanSummary(BaseModel):
    id: int
    run_type: str  # optimized / replanned
    plan_date: date | None
    solver: str | None  # чем посчитан план
    created_at: datetime
    engineers_used: int
    assigned_count: int
    unassigned_count: int
    total_distance_km: float | None = None  # общий пробег по дорогам; у старых планов может не быть


class PlanVisit(BaseModel):
    visit_order: int
    request_id: int
    planned_arrival_time: datetime  # время начала работ
    address: str
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    duration_minutes: int
    priority_id: int


class EngineerRoute(BaseModel):
    engineer_id: int
    engineer_name: str
    transport_id: int
    start_latitude: float
    start_longitude: float
    distance_km: float  # пробег по маршруту от старта до последней заявки
    duration_min: float  # время в пути, без работы на заявках
    provider: str  # valhalla или haversine — чем посчитаны пробег и линия
    geometry: list[str]  # encoded polyline по участкам; пусто, если посчитано по прямой
    visits: list[PlanVisit]


class UnassignedRequest(BaseModel):
    request_id: int
    address: str
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    reason: str | None


class PlanDetail(PlanSummary):
    total_distance_km: float
    routes: list[EngineerRoute]
    unassigned: list[UnassignedRequest]
