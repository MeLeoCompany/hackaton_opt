from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.system import SolverParams
from src.schemas.travel import TravelLeg
from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    validate_objective_order,
)


class SolverName(str, Enum):
    """Чем считать план. Список расширяется по мере появления решателей."""

    CUOPT = "cuopt"
    # тот же поиск маршрутов, но на процессоре: работает без видеокарты (ortools_solver)
    ORTOOLS = "ortools"
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
    # номер запуска: интерфейс придумывает его заранее и по нему показывает ход расчёта
    run_id: UUID | None = None
    # параметры решателя на этот расчёт; пусто — берём системные («Система» → параметры расчёта)
    solver_params: SolverParams | None = None

    @field_validator("objective_order")
    @classmethod
    def validate_order(cls, value: list[ObjectiveCriterion]) -> list[ObjectiveCriterion]:
        return list(validate_objective_order(value))


class ReplanDecision(BaseModel):
    """Что оператор решил по заявке, на которую не успеваем (docs/algoV2.md, шаг 4).

    agree — клиент согласен на предложенное время: окно сужается до обещанного, заявка
    получает отметку «согласовано»; move — клиент сегодня не может: окно уезжает на другой
    день, отметка «перенесена»; cancel — работа не нужна; no_answer — не дозвонились,
    тоже отмена, но с отметкой «требует уточнения».
    """

    request_id: int
    action: Literal["agree", "move", "cancel", "no_answer"]
    window_start: datetime | None = None
    window_end: datetime | None = None
    # почему отменили — словами; у no_answer подставляется сама
    reason: str = ""

    @model_validator(mode="after")
    def check_window(self) -> "ReplanDecision":
        if self.action not in ("agree", "move"):
            return self
        if self.window_start is None or self.window_end is None:
            raise ValueError(f"заявке №{self.request_id} нужно новое окно")
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("время окна — с часовым поясом, например 2026-08-18T10:00:00+03:00")
        if self.window_end <= self.window_start:
            raise ValueError(f"заявка №{self.request_id}: конец окна должен быть позже начала")
        return self


class ReplanProblem(BaseModel):
    """Заявка, на которую при пересчёте не успеваем, — и что можно предложить клиенту."""

    request_id: int
    address: str
    window_start: datetime
    window_end: datetime
    status_id: int
    reason: str
    # окно уже закрылось к моменту пересчёта: разговор с клиентом другой
    expired: bool = False
    # предложение из второго расчёта: когда и кто может приехать; пусто — «сегодня никак»
    suggested_start: datetime | None = None
    suggested_end: datetime | None = None
    suggested_engineer: str | None = None


class ReplanPreview(BaseModel):
    """Пробный пересчёт без сохранения: сколько разложится и на какие заявки не успеваем.

    По невлезшим заявкам второй расчёт подбирает время, которое оператор называет клиенту.
    """

    assigned_count: int
    unassigned: list[ReplanProblem] = []
    # ширина обещанного окна: предложенное время плюс этот допуск
    promise_tolerance_minutes: int = 30


class BrigadeFreeAt(BaseModel):
    """Оператор узнал по телефону, когда бригада освободится (docs/algoV2.md, шаг 10).

    Застрявшая бригада не уложится в норматив, поэтому новый план считается от этого времени,
    а не от планового окончания работы.
    """

    engineer_id: int
    free_at: datetime

    @field_validator("free_at")
    @classmethod
    def with_time_zone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("время освобождения бригады должно быть с часовым поясом")
        return value


class PlanApprovalReviewRequest(BaseModel):
    """Перед утверждением черновика: подобрать окна невлезшим заявкам или учесть решения.

    decisions пусто — список невлезших заявок; с suggest=true к нему идёт второй расчёт
    с раскрытыми окнами («Подобрать окна»), с suggest=false расчёта нет вовсе — оператор
    просто переносит или отменяет заявки и утверждает готовый план.
    """

    decisions: list[ReplanDecision] = []
    # считать ли второй расчёт: он нужен только для подбора окон
    suggest: bool = True
    run_id: UUID | None = None
    solver_params: SolverParams | None = None


class PlanReplanRequest(BaseModel):
    """Пересчёт утверждённого плана: чем считать и на какой момент (пусто — сейчас)."""

    solver: SolverName = SolverName.CUOPT
    objective_order: list[ObjectiveCriterion] = Field(
        default_factory=lambda: list(DEFAULT_OBJECTIVE_ORDER)
    )
    # на какой момент пересчитать: бригады свободны не раньше него. Пусто — текущее время
    at: datetime | None = None
    # решения по заявкам, на которые не успеваем (из пробного пересчёта): применяются до расчёта
    decisions: list[ReplanDecision] = []
    # когда бригады освободятся — со слов бригады, если она застряла
    free_at: list[BrigadeFreeAt] = []
    # номер запуска: по нему интерфейс показывает ход пересчёта
    run_id: UUID | None = None
    # параметры решателя на этот пересчёт; пусто — системные
    solver_params: SolverParams | None = None

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
    # из них «Новых» с уже закрытым окном: хвост прошедшего дня — перенести или отменить
    overdue_requests: int = 0


class WithdrawnRequest(BaseModel):
    """Заявка, снятая с утверждённого плана: status_id говорит как — отменена или «Новая»."""

    request_id: int
    status_id: int


class BrokenPromise(BaseModel):
    """Заявка, которой обещали время, а расчёт его не удержал."""

    request_id: int
    address: str
    promised_from: datetime
    promised_to: datetime
    # когда работа начнётся по новому плану; пусто — заявка в план не попала
    planned_start: datetime | None = None


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
    # пересчёт не вступил в силу: когда это выяснилось и почему. Бригады в это время едут по
    # прежнему плану, а день нужно пересчитать заново — с новыми вводными
    voided_at: datetime | None = None
    void_reason: str | None = None
    # план заменён утверждённым пересчётом: бригады ездят уже по новому
    superseded_at: datetime | None = None
    # какой пересчёт его заменил: по цепочке планов видно, что происходило за день
    replaced_by_plan_id: int | None = None
    # посчитанный пересчёт этого плана, который вот-вот вступит в силу: пока он есть, бригады
    # выезжают только туда, куда ведёт и он (docs/algoV2.md, шаги 6-8)
    pending_replan_id: int | None = None
    # пересчёт этого плана, который в силу не вступил, и почему: повод пересчитать заново
    voided_replan_id: int | None = None
    voided_replan_reason: str | None = None
    # черновик уже не утвердить: на его день действует другой план. Это история расчётов
    outdated: bool = False
    # черновик идущего дня посчитан на выезд в этот момент («сейчас плюс запас»): до него его
    # и утверждают. stale_reason — почему уже поздно или что изменилось в дне с расчёта
    effective_at: datetime | None = None
    stale_reason: str | None = None
    # черновик посчитан после решений оператора по невлезшим заявкам другого черновика
    decisions_from_plan_id: int | None = None
    decisions_count: int | None = None
    # можно ли снять утверждение: у плана, по которому уже работают, — нельзя, только пересчёт
    can_cancel_approval: bool = False
    # только у утверждённого плана: что изменилось с утверждения — повод его пересчитать.
    # Сняты — заявки его маршрутов отменены или возвращены в «Новая» (со статусом: как сняли);
    # новые — заявки дня офиса, которые ждут планирования, а расчёт плана их не видел
    withdrawn_requests: list[WithdrawnRequest] = []
    new_request_ids: list[int] = []
    # из новых — аварии: главный повод пересчитать, авария меняет маршруты бригад
    urgent_request_ids: list[int] = []
    # бригады отстают: к этим заявкам по плану уже не успеть до конца окна
    at_risk_request_ids: list[int] = []
    # обещания клиентам, которые этот расчёт не удержал: заявка согласована на время,
    # но в план не попала или стоит вне обещанного окна (docs/algoV2.md, шаг 5)
    broken_promises: list["BrokenPromise"] = []


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
    # оператор разрешил выезд, хотя бригада отстаёт (docs/algoV2.md, шаг 9)
    departure_allowed_at: datetime | None = None
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
    # утверждённый план: на сколько бригада отстаёт по своим отметкам и к каким заявкам
    # маршрута уже не успеет к концу окна (route_delay.py)
    delay_minutes: int = 0
    at_risk_request_ids: list[int] = []
    # телефон бригады: оператор звонит прямо из плана (docs/algoV2.md, шаг 8)
    phone: str | None = None
    # бригада выбилась из плана и ждёт нового: выезд на следующую заявку закрыт
    waiting_request_id: int | None = None
    waiting_reason: str | None = None
    # с какого времени ждёт (плановое начало ближайшей заявки) и почему кодом:
    # replan_pending — идёт пересчёт, not_departed — не выехала, at_risk — к окну не успеть
    waiting_since: datetime | None = None
    waiting_cause: str | None = None
    # бригада сейчас на заявке: когда она освободится, если пересчитать день сейчас. Диалог
    # пересчёта подставляет это время в «освободится в» (docs/algoV2.md, шаг 10)
    free_at_estimate: datetime | None = None
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


class PlanSyncRequest(BaseModel):
    """Какие маршруты привести к плану — по бригадам (режим демонстрации)."""

    engineer_ids: list[int] = Field(min_length=1)


class PlanSyncReport(BaseModel):
    """Что получилось после синхронизации: сколько заявок в каком статусе и сам план."""

    routes: int
    done: int
    in_progress: int
    en_route: int
    planned: int
    plan: PlanDetail
