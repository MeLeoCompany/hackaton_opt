from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

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


class PlanReplanRequest(BaseModel):
    """Пересчёт утверждённого плана: чем считать и на какой момент (пусто — сейчас)."""

    solver: SolverName = SolverName.CUOPT
    objective_order: list[ObjectiveCriterion] = Field(
        default_factory=lambda: list(DEFAULT_OBJECTIVE_ORDER)
    )
    # на какой момент пересчитать: бригады свободны не раньше него. Пусто — текущее время
    at: datetime | None = None

    @field_validator("objective_order")
    @classmethod
    def validate_order(cls, value: list[ObjectiveCriterion]) -> list[ObjectiveCriterion]:
        return list(validate_objective_order(value))

    @field_validator("at")
    @classmethod
    def with_time_zone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError(
                "момент пересчёта — с часовым поясом, например 2026-08-17T14:30:00+03:00"
            )
        return value


class PlanningDayOption(BaseModel):
    """День, на который есть активные заявки."""

    plan_date: date
    active_requests: int


class WithdrawnRequest(BaseModel):
    """Заявка, снятая с утверждённого плана: status_id говорит как — отменена или «Новая»."""

    request_id: int
    status_id: int


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
    # пересчёт с текущего момента: какой план пересчитан и на какой момент
    parent_plan_id: int | None = None
    replanned_at: datetime | None = None
    # план заменён утверждённым пересчётом: бригады ездят уже по новому
    superseded_at: datetime | None = None
    # только у утверждённого плана: что изменилось с утверждения — повод его пересчитать.
    # Сняты — заявки его маршрутов отменены или возвращены в «Новая» (со статусом: как сняли);
    # новые — заявки дня офиса, которые ждут планирования, а расчёт плана их не видел
    withdrawn_requests: list[WithdrawnRequest] = []
    new_request_ids: list[int] = []
    # бригады отстают: к этим заявкам по плану уже не успеть до конца окна
    at_risk_request_ids: list[int] = []


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
    # статус заявки сейчас: по нему видно, какие визиты маршрута уже закрыты
    status_id: int
    # за каким утверждённым планом заявка закреплена сейчас; у утверждённого плана визит,
    # чья заявка закреплена не за ним, снят с плана (заявку вернули в «Новая»)
    approved_plan_id: int | None = None
    # что отметила бригада в мобильном приложении: выехала, прибыла, закончила
    departed_at: datetime | None = None
    arrived_at: datetime | None = None
    finished_at: datetime | None = None
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
    # утверждённый план: на сколько бригада отстаёт по своим отметкам и к каким заявкам
    # маршрута уже не успеет к концу окна (route_delay.py)
    delay_minutes: int = 0
    at_risk_request_ids: list[int] = []
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
