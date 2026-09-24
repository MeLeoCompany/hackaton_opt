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
from datetime import datetime, timedelta

from src.core import clock
from src.core.config import settings
from src.schemas.plans import SolverName
from src.schemas.system import SolverParams
from src.services.planner import planning_service
from src.services.planner.objective_policy import ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import round_ranks


@dataclass(frozen=True)
class WindowSuggestion:
    """Что можно пообещать клиенту: когда приедет бригада и какая."""

    request_id: int
    start: datetime
    engineer_name: str


def widened_instance(loaded: LoadedDay, widened_indices: set[int]):
    """Копия задачи с раскрытым окном невлезших: [max(t0; T); самый поздний конец смены].

    T — момент, с которого считаем: сейчас плюс запас на расчёт и обзвон
    (settings.replan_lead_minutes, docs/algoV2.md, шаг 2). Раньше него предлагать время
    нельзя: эти минуты бригады ещё едут по прежнему плану, и обещание клиенту было бы
    заведомо невыполнимым. Для будущего дня T лежит до начала дня и ничего не меняет.
    В базе окна не трогаем — раскрытие живёт только внутри расчёта.
    """
    instance = copy.copy(loaded.instance)
    latest_shift_end = max(engineer.shift_end_min for engineer in instance.engineers)
    not_before = loaded.day.to_minutes(
        clock.now() + timedelta(minutes=settings.replan_lead_minutes), round_up=True
    )
    instance.requests = [
        replace(
            request,
            window_start_min=max(request.window_start_min, not_before),
            window_end_min=max(request.window_end_min, latest_shift_end),
        )
        if index in widened_indices
        else request
        for index, request in enumerate(instance.requests)
    ]
    return instance


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
    # ярус B: кто влез в первый расчёт. Их нельзя выкинуть ради раскрытой заявки —
    # иначе появится новая жертва и новый звонок (docs/algoV2.md, шаг 3)
    kept_request_ids = {
        request.request_id
        for index, request in enumerate(loaded.instance.requests)
        if index not in widened_indices
    }
    solution = await planning_service.solve_with(
        solver,
        probe,
        objective_order,
        round_ranks(loaded.instance.requests, kept_request_ids),
        params=params,
        kept_request_ids=kept_request_ids,
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
