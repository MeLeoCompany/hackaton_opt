"""Сборка задачи планирования на один день из БД: БД -> ProblemInstance.

В задачу дня офиса попадают:
  - заявки офиса: активные, окно которых пересекается с этим днём;
  - бригады офиса: смена которых пересекается с этим днём.

Время переводится в целые минуты от 00:00 этого дня по Москве и обрезается границами дня.
Матрицы считаются по одной на каждый вид транспорта: Valhalla для автомобильных,
пешеходных и велосипедных поездок, R5 с данными Valhalla для общественного транспорта.
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ExternalServiceError
from src.core.local_day import local_timezone
from src.models import Engineer, Request
from src.repositories.engineers import engineers_repository
from src.repositories.references import references_repository
from src.repositories.requests import requests_repository
from src.schemas.travel import Point, TransportKind
from src.services.planner import run_log
from src.services.planner.planner_problem import (
    LOWEST_PRIORITY_LEVEL,
    EngineerSpec,
    ProblemInstance,
    RequestSpec,
    build_compatibility,
)
from src.services.travel import build_matrix

MINUTES_IN_DAY = 24 * 60

# если между точками нет дороги, пару заменяем заведомо непроходимым значением:
# решатели не принимают бесконечность
UNREACHABLE_MINUTES = 100_000
UNREACHABLE_KM = 100_000.0

# как приоритет и транспорт называются в журнале расчёта
PRIORITY_NAMES = {1: "аварийные", 2: "высокий", 3: "обычный"}
TRANSPORT_NAMES = {
    TransportKind.CAR.value: "автомобиль",
    TransportKind.PEDESTRIAN.value: "пешком",
    TransportKind.BICYCLE.value: "велосипед",
    TransportKind.PUBLIC_TRANSPORT.value: "общественный транспорт",
}


@dataclass(frozen=True)
class PlanningDay:
    plan_date: date
    day_start: datetime  # 00:00 этого дня по Москве
    day_end: datetime  # 00:00 следующего дня

    def to_minutes(self, moment: datetime, *, round_up: bool = False) -> int:
        """Момент времени -> минуты от начала дня, обрезанные границами дня."""
        offset = (moment - self.day_start).total_seconds() / 60
        minutes = math.ceil(offset) if round_up else math.floor(offset)
        return min(max(minutes, 0), MINUTES_IN_DAY)

    def from_minutes(self, minutes: float) -> datetime:
        """Минуты от начала дня -> момент времени."""
        return self.day_start + timedelta(minutes=float(minutes))


@dataclass(frozen=True)
class EngineerStart:
    """Пересчёт с текущего момента: откуда бригада стартует и с какого времени свободна.

    Бригада уже работает: стоит на последней выполненной заявке или едет на текущую. Решатель
    берёт эту точку вместо утреннего старта, а начало смены — не раньше available_from.
    """

    latitude: float
    longitude: float
    available_from: datetime


@dataclass
class LoadedDay:
    day: PlanningDay
    office_id: int  # чей день: заявки и бригады только этого офиса
    instance: ProblemInstance
    requests: list[Request]  # в том же порядке, что instance.requests
    engineers: list[Engineer]  # в том же порядке, что instance.engineers, навыки загружены
    skill_names: dict[int, str]
    transport_names: dict[int, str]
    start_points: list[Point] | None = None  # фактические старты при пересчёте


def planning_day(plan_date: date) -> PlanningDay:
    day_start = datetime.combine(plan_date, time.min, tzinfo=local_timezone())
    return PlanningDay(
        plan_date=plan_date, day_start=day_start, day_end=day_start + timedelta(days=1)
    )


def local_date_of(moment: datetime) -> date:
    """Московская дата момента времени."""
    return moment.astimezone(local_timezone()).date()


async def load_day(
    session: AsyncSession,
    day: PlanningDay,
    office_id: int,
    *,
    starts: dict[int, EngineerStart] | None = None,
    not_before: datetime | None = None,
) -> LoadedDay:
    """starts — пересчёт с текущего момента: у бригады своя точка старта и время, с которого
    она свободна. В LoadedDay.engineers остаются сами бригады (для снимка и отображения
    плана), подмена — только в задаче решателя."""
    starts = starts or {}
    # not_before — момент пересчёта: раньше него не свободна ни одна бригада
    # офисы изолированы: бригады офиса берут только заявки своего офиса.
    # Заявки, закреплённые за утверждённым планом другого дня, в задачу не попадают:
    # окно через полночь иначе выполнялось бы дважды
    async with run_log.step("Читаю заявки и смены дня", 2, 10):
        requests = await requests_repository.list_active_requests_in_period(
            session, day.day_start, day.day_end, plan_date=day.plan_date, office_id=office_id
        )
        engineers = await engineers_repository.list_engineers_in_period(
            session, day.day_start, day.day_end, office_id=office_id
        )
        await run_log.note(
            f"заявок к планированию {len(requests)}, смен бригад {len(engineers)}",
            details={"requests": len(requests), "engineers": len(engineers)},
        )


    def free_from(engineer: Engineer) -> datetime:
        start = starts.get(engineer.id)
        moments = [engineer.shift_start]
        if start is not None:
            moments.append(start.available_from)
        if not_before is not None:
            moments.append(not_before)
        return max(moments)

    # бригада, у которой смена уже закончилась к моменту пересчёта, в задачу не идёт
    engineers = [
        e
        for e in engineers
        if day.to_minutes(free_from(e), round_up=True) <= day.to_minutes(e.shift_end)
    ]
    skills = await references_repository.list_skills(session)
    transports = await references_repository.list_transports(session)
    priorities = await references_repository.list_priorities(session)
    priority_levels = {priority.id: priority.level for priority in priorities}
    await describe_day(requests, engineers, priority_levels)

    start_points = [
        Point(latitude=starts[e.id].latitude, longitude=starts[e.id].longitude)
        if e.id in starts
        else Point(latitude=float(e.start_latitude), longitude=float(e.start_longitude))
        for e in engineers
    ]
    distance_km, travel_min = await build_day_matrices(
        engineers, requests, start_points, day_start=day.day_start
    )

    instance = ProblemInstance(
        engineers=[
            EngineerSpec(
                engineer_id=engineer.id,
                name=engineer.name,
                transport_id=engineer.transport_id,
                shift_start_min=day.to_minutes(free_from(engineer), round_up=True),
                shift_end_min=day.to_minutes(engineer.shift_end),
            )
            for engineer in engineers
        ],
        requests=[
            RequestSpec(
                request_id=request.id,
                duration_min=request.duration_minutes,
                window_start_min=day.to_minutes(request.window_start, round_up=True),
                window_end_min=day.to_minutes(request.window_end),
                skill_id=request.skill_id,
                required_transport_id=request.transport_id,
                priority_level=priority_levels.get(request.priority_id, LOWEST_PRIORITY_LEVEL),
                # отметки синхронизации: обещание клиенту и перенос с другого дня (036)
                promised=request.promised_from is not None,
                moved=request.moved_from is not None,
            )
            for request in requests
        ],
        distance_km=distance_km,
        travel_min=travel_min,
    )
    build_compatibility(
        instance, {engineer.id: {skill.id for skill in engineer.skills} for engineer in engineers}
    )

    return LoadedDay(
        day=day,
        office_id=office_id,
        instance=instance,
        requests=requests,
        engineers=engineers,
        skill_names={skill.id: skill.name for skill in skills},
        transport_names={transport.id: transport.name for transport in transports},
        start_points=start_points,
    )


async def describe_day(
    requests: list[Request], engineers: list[Engineer], priority_levels: dict[int, int]
) -> None:
    """Пишет в журнал состав дня: из чего вообще складывается задача."""
    if not requests and not engineers:
        return
    levels = Counter(
        priority_levels.get(request.priority_id, LOWEST_PRIORITY_LEVEL) for request in requests
    )
    by_level = ", ".join(
        f"{PRIORITY_NAMES.get(level, level)} — {count}" for level, count in sorted(levels.items())
    )
    promised = sum(1 for request in requests if request.promised_from is not None)
    moved = sum(1 for request in requests if request.moved_from is not None)
    work_minutes = sum(request.duration_minutes for request in requests)
    await run_log.note(
        f"Заявки по приоритетам: {by_level}" if requests else "Заявок на день нет",
        details={"by_priority": {str(level): count for level, count in levels.items()}},
    )
    if promised or moved:
        await run_log.note(
            f"С отметками: согласовано — {promised}, перенесённых — {moved}",
            details={"promised": promised, "moved": moved},
        )
    if engineers:
        transports = Counter(engineer.transport_id for engineer in engineers)
        by_transport = ", ".join(
            f"{TRANSPORT_NAMES.get(transport_id, transport_id)} — {count}"
            for transport_id, count in sorted(transports.items())
        )
        shift_start = min(engineer.shift_start for engineer in engineers)
        shift_end = max(engineer.shift_end for engineer in engineers)
        await run_log.note(
            f"Бригады: {by_transport}; смены с {local_text(shift_start)} до {local_text(shift_end)}",
            details={"by_transport": {str(key): value for key, value in transports.items()}},
        )
    await run_log.note(
        f"Работы в заявках на {work_minutes // 60} ч {work_minutes % 60} мин",
        details={"work_minutes": work_minutes},
    )


async def describe_matrix(travel_min: np.ndarray, provider=None) -> None:
    """Что получилось в матрице: сколько ехать между точками и куда дороги нет."""
    reachable = travel_min[travel_min < UNREACHABLE_MINUTES]
    unreachable = int((travel_min >= UNREACHABLE_MINUTES).sum())
    pairs = travel_min.size
    if reachable.size == 0:
        await run_log.note(
            f"Матрица {pairs} пар: доехать нельзя ни до одной точки", level="warning"
        )
        return
    await run_log.note(
        f"Матрица {pairs} пар{provider_text(provider)}: в пути в среднем "
        f"{reachable.mean():.0f} мин, дольше всего {reachable.max():.0f} мин"
        + (f", без дороги {unreachable} пар" if unreachable else ""),
        level="warning" if unreachable else "info",
        details={
            "pairs": pairs,
            "unreachable": unreachable,
            "mean_minutes": round(float(reachable.mean()), 1),
            "max_minutes": int(reachable.max()),
        },
    )


def provider_text(provider) -> str:
    """Чем посчитана матрица: valhalla, r5, haversine — если провайдер известен."""
    name = getattr(provider, "value", provider)
    return f" ({name})" if name else ""


def local_text(moment: datetime) -> str:
    return moment.astimezone(local_timezone()).strftime("%H:%M")


async def build_day_matrices(
    engineers: list[Engineer],
    requests: list[Request],
    start_points: list[Point] | None = None,
    *,
    day_start: datetime | None = None,
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Матрицы км и минут по всем точкам дня — отдельно для каждого типа транспорта исполнителей.

    Порядок точек: сначала старты исполнителей, потом адреса заявок — как в ProblemInstance.
    """
    if not engineers or not requests:
        return {}, {}

    # старты бригад: утренние или (при пересчёте) там, где бригада сейчас
    points = (
        list(start_points)
        if start_points is not None
        else [
            Point(
                latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude)
            )
            for engineer in engineers
        ]
    )
    points += [
        Point(latitude=float(request.latitude), longitude=float(request.longitude))
        for request in requests
    ]

    distance_km: dict[int, np.ndarray] = {}
    travel_min: dict[int, np.ndarray] = {}
    # матрицы — самая долгая часть дня: на каждый транспорт свой шаг журнала
    transport_ids = sorted({engineer.transport_id for engineer in engineers})
    matrix_span = (45 - 10) / len(transport_ids)
    for order, transport_id in enumerate(transport_ids):
        async with run_log.step(
            f"Считаю матрицу расстояний: {TRANSPORT_NAMES[transport_id]} ({len(points)} точек)",
            round(10 + matrix_span * order),
            round(10 + matrix_span * (order + 1)),
        ):
            transport_engineers = [
                engineer for engineer in engineers if engineer.transport_id == transport_id
            ]
            departure_time = min(
                max(engineer.shift_start, day_start)
                if day_start is not None
                else engineer.shift_start
                for engineer in transport_engineers
            )
            try:
                matrix = await build_matrix(
                    points,
                    TransportKind(transport_id),
                    departure_time=departure_time,
                    allow_fallback=False,
                )
            except (httpx.HTTPError, KeyError, ValueError) as error:
                raise ExternalServiceError(
                    f"Маршрутизатор недоступен, матрицу расстояний посчитать нельзя: {error}"
                ) from error

            distance_km[transport_id] = replace_unreachable(matrix.distances_km, UNREACHABLE_KM)
            travel_min[transport_id] = np.ceil(
                replace_unreachable(matrix.durations_min, UNREACHABLE_MINUTES)
            ).astype(np.int32)
            await describe_matrix(travel_min[transport_id], getattr(matrix, "provider", None))

    return distance_km, travel_min


def replace_unreachable(values: list[list[float | None]], unreachable: float) -> np.ndarray:
    """Матрица из маршрутизатора -> numpy; пары без дороги (бесконечность) -> значение unreachable."""
    matrix = np.array(values, dtype=float)
    matrix[~np.isfinite(matrix)] = unreachable
    return matrix
