from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from src.schemas.travel import TravelLeg
from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    validate_objective_order,
)


class SolverName(str, Enum):
    """Чем считать план. Список расширяется по мере появления решателей."""

    CUOPT = "cuopt"
    BASELINE = "baseline"


class PlanBuildRequest(BaseModel):
    """Параметры расчёта: день и чем считать.

    Сюда же добавляются будущие параметры (лимит времени, веса целевой функции): каждый
    расчёт — отдельный план со своими параметрами, и потом любые два плана можно сравнить.
    """

    plan_date: date
    solver: SolverName = SolverName.CUOPT
    objective_order: list[ObjectiveCriterion] = Field(
        default_factory=lambda: list(DEFAULT_OBJECTIVE_ORDER)
    )

    @field_validator("objective_order")
    @classmethod
    def validate_order(cls, value: list[ObjectiveCriterion]) -> list[ObjectiveCriterion]:
        return list(validate_objective_order(value))


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
    urgent_assigned_count: int | None = None
    unassigned_count: int
    total_distance_km: float | None = None  # общий пробег по дорогам; у старых планов может не быть
    distance_provider: str | None = None  # valhalla / haversine / mixed; NULL у старых планов
    solve_duration_ms: float | None = None
    approved_at: datetime | None = None  # план утверждён: его заявки закреплены за этим днём
    objective_order: list[ObjectiveCriterion] | None = None


class HeldRequest(BaseModel):
    """Заявка дня, закреплённая за утверждённым планом другого дня."""

    request_id: int
    address: str
    window_start: datetime
    window_end: datetime
    plan_id: int
    plan_date: date


class PlanDayCheck(BaseModel):
    """Что ждёт диспетчера перед расчётом дня: сколько заявок и какие из них уже заняты."""

    plan_date: date
    active_requests: int
    approved_plan_id: int | None = None  # утверждённый план этого дня, если он есть
    held_requests: list[HeldRequest] = []


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
    # факты этого визита — из них интерфейс объясняет, почему он стоит здесь
    available_from: datetime  # когда исполнитель освободился: конец прошлой работы или начало смены
    window_slack_minutes: int  # запас до закрытия окна заявки
    shift_slack_minutes: int  # запас до конца смены после этой работы
    candidate_engineers: int | None = None  # сколько бригад дня могли взять заявку


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
    legs: list[TravelLeg] = Field(
        default_factory=list
    )  # режим, ожидание и остановки каждого участка
    shift_start: datetime
    shift_end: datetime
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
