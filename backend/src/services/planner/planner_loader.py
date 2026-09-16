"""Сборка задачи планирования на один день из БД: БД -> ProblemInstance.

В задачу дня попадают:
  - заявки: активные, окно которых пересекается с этим днём;
  - исполнители: смена которых пересекается с этим днём.

Время переводится в целые минуты от 00:00 этого дня по Москве и обрезается границами дня.
Матрицы расстояний и времени в пути считаются через Valhalla — по одной паре на каждый тип
транспорта, который есть у отобранных исполнителей.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

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
from src.services.planner.planner_problem import (
    EngineerSpec,
    ProblemInstance,
    RequestSpec,
    build_compatibility,
)
from src.services.travel import build_matrix

MINUTES_IN_DAY = 24 * 60

URGENT_PRIORITY_NAME = "Срочная"
URGENT_PRIORITY_WEIGHT = 100.0

# если между точками нет дороги, пару заменяем заведомо непроходимым значением:
# решатели не принимают бесконечность
UNREACHABLE_MINUTES = 100_000
UNREACHABLE_KM = 100_000.0


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


@dataclass
class LoadedDay:
    day: PlanningDay
    instance: ProblemInstance
    requests: list[Request]  # в том же порядке, что instance.requests
    engineers: list[Engineer]  # в том же порядке, что instance.engineers, навыки загружены
    skill_names: dict[int, str]
    transport_names: dict[int, str]


def planning_day(plan_date: date) -> PlanningDay:
    day_start = datetime.combine(plan_date, time.min, tzinfo=local_timezone())
    return PlanningDay(plan_date=plan_date, day_start=day_start, day_end=day_start + timedelta(days=1))


def local_date_of(moment: datetime) -> date:
    """Московская дата момента времени."""
    return moment.astimezone(local_timezone()).date()


async def load_day(session: AsyncSession, day: PlanningDay) -> LoadedDay:
    requests = await requests_repository.list_active_requests_in_period(session, day.day_start, day.day_end)
    engineers = await engineers_repository.list_engineers_in_period(session, day.day_start, day.day_end)
    engineers = [e for e in engineers
                 if day.to_minutes(e.shift_start, round_up=True) <= day.to_minutes(e.shift_end)]
    skills = await references_repository.list_skills(session)
    transports = await references_repository.list_transports(session)
    priorities = await references_repository.list_priorities(session)
    urgent_priority_ids = {priority.id for priority in priorities if priority.name == URGENT_PRIORITY_NAME}

    distance_km, travel_min = await build_day_matrices(engineers, requests)

    instance = ProblemInstance(
        engineers=[
            EngineerSpec(
                engineer_id=engineer.id,
                name=engineer.name,
                transport_id=engineer.transport_id,
                shift_start_min=day.to_minutes(engineer.shift_start, round_up=True),
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
                priority_weight=URGENT_PRIORITY_WEIGHT if request.priority_id in urgent_priority_ids else 1.0,
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
        instance=instance,
        requests=requests,
        engineers=engineers,
        skill_names={skill.id: skill.name for skill in skills},
        transport_names={transport.id: transport.name for transport in transports},
    )


async def build_day_matrices(
    engineers: list[Engineer], requests: list[Request]
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Матрицы км и минут по всем точкам дня — отдельно для каждого типа транспорта исполнителей.

    Порядок точек: сначала старты исполнителей, потом адреса заявок — как в ProblemInstance.
    """
    if not engineers or not requests:
        return {}, {}

    points = [
        Point(latitude=float(engineer.start_latitude), longitude=float(engineer.start_longitude))
        for engineer in engineers
    ]
    points += [Point(latitude=float(request.latitude), longitude=float(request.longitude)) for request in requests]

    distance_km: dict[int, np.ndarray] = {}
    travel_min: dict[int, np.ndarray] = {}
    for transport_id in sorted({engineer.transport_id for engineer in engineers}):
        try:
            matrix = await build_matrix(points, TransportKind(transport_id), allow_fallback=False)
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ExternalServiceError(
                f"Маршрутизатор Valhalla недоступен, матрицу расстояний посчитать нельзя: {error}"
            ) from error

        distance_km[transport_id] = replace_unreachable(matrix.distances_km, UNREACHABLE_KM)
        travel_min[transport_id] = np.ceil(replace_unreachable(matrix.durations_min, UNREACHABLE_MINUTES)).astype(
            np.int32
        )

    return distance_km, travel_min


def replace_unreachable(values: list[list[float]], unreachable: float) -> np.ndarray:
    """Матрица из маршрутизатора -> numpy; пары без дороги (бесконечность) -> значение unreachable."""
    matrix = np.array(values, dtype=float)
    matrix[~np.isfinite(matrix)] = unreachable
    return matrix
