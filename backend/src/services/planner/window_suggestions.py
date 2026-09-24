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

from dataclasses import dataclass
from datetime import datetime

from src.schemas.plans import SolverName
from src.schemas.system import SolverParams
from src.services.planner import planner_loader, planning_service
from src.services.planner.objective_policy import ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import round_ranks


@dataclass(frozen=True)
class WindowSuggestion:
    """Что можно пообещать клиенту: когда приедет бригада и какая."""

    request_id: int
    start: datetime
    engineer_name: str


@dataclass(frozen=True)
class WindowSearch:
    """Результат второго расчёта: что предложить клиентам и сам расклад дня.

    Расклад сохраняется как новый расчёт дня: клиент согласился — заявка остаётся ровно там,
    куда её поставил этот расчёт, отказался — её вычёркивают. Считать день ещё раз незачем
    (docs/algoV2.md, шаги 3-5).
    """

    suggestions: dict[int, WindowSuggestion]
    solution: object | None = None
    loaded: LoadedDay | None = None


async def suggest_windows(
    loaded: LoadedDay,
    solver: SolverName,
    objective_order: tuple[ObjectiveCriterion, ...],
    unassigned_request_ids: set[int],
    params: SolverParams | None = None,
) -> WindowSearch:
    """Предложения по номеру заявки и расклад, которым они получены.

    Кого не взяли и здесь — «сегодня никак»: такой заявке предложения не будет.
    """
    widened_indices = {
        index
        for index, request in enumerate(loaded.instance.requests)
        if request.request_id in unassigned_request_ids
    }
    if not widened_indices or loaded.instance.n_engineers == 0:
        return WindowSearch(suggestions={})

    # ярус B: кто влез в первый расчёт. Их нельзя выкинуть ради раскрытой заявки —
    # иначе появится новая жертва и новый звонок (docs/algoV2.md, шаг 3)
    probe, kept_request_ids = planner_loader.widen_day(loaded, unassigned_request_ids)
    instance = probe.instance
    solution = await planning_service.solve_with(
        solver,
        probe,
        objective_order,
        round_ranks(loaded.instance.requests, kept_request_ids),
        params=params,
        kept_request_ids=kept_request_ids,
    )
    suggestions = {
        request.request_id: WindowSuggestion(
            request_id=request.request_id,
            start=loaded.day.from_minutes(visit.work_start_minute),
            engineer_name=loaded.engineers[engineer_index].name,
        )
        for engineer_index, visits in solution.routes.items()
        for visit in visits
        if (request := instance.requests[visit.request_index]).request_id in unassigned_request_ids
    }
    return WindowSearch(suggestions=suggestions, solution=solution, loaded=probe)
