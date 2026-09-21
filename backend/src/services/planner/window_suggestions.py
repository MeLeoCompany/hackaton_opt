"""Второй расчёт при синхронизации: что можно предложить клиенту по невлезшим заявкам.

Первый расчёт показывает, кого решатель не взял (множество Y). Чтобы оператору было что
сказать клиенту, этим заявкам временно раскрывают окно до конца самой поздней смены дня
и считают ещё раз. В базе окна не меняются — раскрытие живёт только внутри расчёта
(docs/algoV2.md, шаги 2 и 3).

Ярусы второго расчёта:
  A1 — аварии, откуда бы ни были;
  B1 — заявки, которые влезли в первый расчёт: их нельзя вытеснять, иначе появится
       новая жертва и новый звонок;
  C1 — раскрытые;
  D1 — дальше как обычно (максимум заявок, бригады, пробег).
Внутри B1 и C1 порядок обычный: обещание, перенос, приоритет.
"""

import copy
from dataclasses import dataclass, replace
from datetime import datetime

from src.schemas.plans import SolverName
from src.schemas.system import SolverParams
from src.services.planner import planning_service
from src.services.planner.objective_policy import ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import (
    RANK_EMERGENCY,
    TOP_PRIORITY_LEVEL,
    WIDENED_RANK_SHIFT,
)


@dataclass(frozen=True)
class WindowSuggestion:
    """Что можно пообещать клиенту: когда приедет бригада и какая."""

    request_id: int
    start: datetime
    engineer_name: str


def widened_instance(loaded: LoadedDay, widened_indices: set[int]):
    """Копия задачи, где у невлезших заявок окно раскрыто до конца самой поздней смены."""
    instance = copy.copy(loaded.instance)
    latest_shift_end = max(engineer.shift_end_min for engineer in instance.engineers)
    instance.requests = [
        replace(request, window_end_min=latest_shift_end)
        if index in widened_indices and request.window_end_min < latest_shift_end
        else request
        for index, request in enumerate(instance.requests)
    ]
    return instance


def widened_ranks(loaded: LoadedDay, widened_indices: set[int]) -> dict[int, int]:
    """Ярусы второго расчёта: аварии сверху, влезшие выше раскрытых."""
    ranks = {}
    for index, request in enumerate(loaded.instance.requests):
        if request.priority_level == TOP_PRIORITY_LEVEL:
            ranks[index] = RANK_EMERGENCY
        elif index in widened_indices:
            ranks[index] = request.objective_rank + WIDENED_RANK_SHIFT
        else:
            ranks[index] = request.objective_rank
    return ranks


async def suggest_windows(
    loaded: LoadedDay,
    solver: SolverName,
    objective_order: tuple[ObjectiveCriterion, ...],
    unassigned_request_ids: set[int],
    params: SolverParams | None = None,
) -> dict[int, WindowSuggestion]:
    """Предложения по номеру заявки; кого не взяли и здесь — «сегодня никак»."""
    widened_indices = {
        index
        for index, request in enumerate(loaded.instance.requests)
        if request.request_id in unassigned_request_ids
    }
    if not widened_indices or loaded.instance.n_engineers == 0:
        return {}

    instance = widened_instance(loaded, widened_indices)
    probe = copy.copy(loaded)
    probe.instance = instance
    solution = await planning_service.solve_with(
        solver, probe, objective_order, widened_ranks(loaded, widened_indices), params=params
    )
    return {
        request.request_id: WindowSuggestion(
            request_id=request.request_id,
            start=loaded.day.from_minutes(visit.work_start_minute),
            engineer_name=loaded.engineers[engineer_index].name,
        )
        for engineer_index, visits in solution.routes.items()
        for visit in visits
        if (request := instance.requests[visit.request_index]).request_id in unassigned_request_ids
    }
