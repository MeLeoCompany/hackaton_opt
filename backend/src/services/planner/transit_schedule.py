"""Проверка маршрутов ОТ по времени фактического выезда между заявками."""

import copy
import logging
import math
from collections import Counter

import httpx
import numpy as np

from src.core.errors import ExternalServiceError
from src.schemas.system import SolverParams
from src.schemas.travel import Point, TransportKind
from src.services.planner import cuopt_solver, run_log
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import ProblemInstance
from src.services.travel import build_route

TRANSIT_ID = TransportKind.PUBLIC_TRANSPORT.value
logger = logging.getLogger(__name__)


def node_points(loaded: LoadedDay) -> list[Point]:
    starts = loaded.start_points or [
        Point(latitude=float(e.start_latitude), longitude=float(e.start_longitude))
        for e in loaded.engineers
    ]
    return [
        *starts,
        *(Point(latitude=float(r.latitude), longitude=float(r.longitude)) for r in loaded.requests),
    ]


async def check_schedule(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    *,
    skip_infeasible: bool = False,
    report: bool = True,
) -> tuple[cuopt_solver.DaySolution | None, dict[tuple[int, int], int]]:
    """Пересчитать начала работ; при нарушении вернуть замеры для следующей попытки."""
    instance = loaded.instance
    routes = dict(solution.routes)
    observations: dict[tuple[int, int], int] = {}
    valid = True
    skipped = 0
    transit_routes = sum(
        1
        for index, visits in solution.routes.items()
        if instance.engineers[index].transport_id == TRANSIT_ID and visits
    )
    checked_routes = 0
    broken: list[str] = []
    if transit_routes and report:
        await run_log.note(f"R5: проверяю расписание по {transit_routes} маршрутам")
    for engineer_index, visits in solution.routes.items():
        engineer = instance.engineers[engineer_index]
        if engineer.transport_id != TRANSIT_ID or not visits:
            continue
        available = engineer.shift_start_min
        previous = instance.start_node(engineer_index)
        actual_visits = []
        for visit in visits:
            next_node = instance.request_node(visit.request_index)
            key = (previous, next_node, available)
            if key not in cache:
                try:
                    route = await build_route(
                        [points[previous], points[next_node]],
                        TransportKind.PUBLIC_TRANSPORT,
                        departure_time=loaded.day.from_minutes(available),
                        allow_fallback=False,
                    )
                except (httpx.HTTPError, KeyError, ValueError) as error:
                    raise ExternalServiceError(
                        f"R5 не смог проверить расписание плана: {error}"
                    ) from error
                cache[key] = math.ceil(route.duration_min - 1e-9)
            duration = cache[key]
            observations[previous, next_node] = max(
                observations.get((previous, next_node), 0), duration
            )
            request = instance.requests[visit.request_index]
            start = max(available + duration, request.window_start_min)
            late_for_window = start > request.window_end_min
            out_of_shift = start + request.duration_min > engineer.shift_end_min
            if late_for_window or out_of_shift:
                broken.append(
                    f"№{request.request_id} у бригады {engineer.name}: "
                    + (
                        f"приедет в {hhmm(start)}, окно до {hhmm(request.window_end_min)}"
                        if late_for_window
                        else f"работа до {hhmm(start + request.duration_min)}, "
                        f"смена до {hhmm(engineer.shift_end_min)}"
                    )
                )
                if skip_infeasible:
                    skipped += 1
                    # Следующее плечо строится от последней выполненной заявки,
                    # а не от пропущенного адреса.
                    continue
                valid = False
            actual_visits.append(cuopt_solver.PlannedVisit(visit.request_index, start))
            available = start + request.duration_min
            previous = next_node
        routes[engineer_index] = actual_visits
        checked_routes += 1
        if report:
            await run_log.check_cancelled()
            await run_log.note(
                f"R5: маршрут {checked_routes} из {transit_routes} — бригада {engineer.name}"
            )
    if broken and report:
        # видно, из-за чего план отвергнут: время из матрицы было оптимистичнее расписания
        await run_log.note(
            f"По фактическому расписанию не сходится {run_log.plural(len(broken), 'визит', 'визита', 'визитов')}",
            level="warning",
            details={"broken": broken[:20]},
        )
        for reason in broken[:5]:
            await run_log.note(reason, level="warning")
    if skipped and report:
        logger.warning("R5: %s визитов не вошло в проверенный вариант", skipped)
        await run_log.note(
            f"Проверенный вариант без визитов, к которым не успеть: снято {skipped}",
            level="warning",
        )
    return (cuopt_solver.DaySolution(routes) if valid else None), observations


def hhmm(minutes: float) -> str:
    """Минуты от начала дня — в часы и минуты: журнал читают люди."""
    total = int(minutes)
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def checked_solution_score(
    instance: ProblemInstance,
    solution: cuopt_solver.DaySolution,
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None,
) -> tuple[float, ...]:
    """Сравнить проверенные R5 варианты по той же иерархии, что использует cuOpt.

    Пробег здесь матричный, как в цели cuOpt; точный пробег по маршрутам измеряется позже.
    """
    assigned = [visit.request_index for visits in solution.routes.values() for visit in visits]
    rank_of = {
        index: (ranks or {}).get(index, instance.requests[index].objective_rank)
        for index in cuopt_solver.schedulable_request_indices(instance)
    }
    counts = Counter(rank_of[index] for index in assigned)
    # У самого нижнего яруса нет отдельной ступени в cuOpt: он учитывается общим числом заявок.
    tiers = tuple(counts[rank] for rank in sorted(set(rank_of.values()))[:-1])
    distance = 0.0
    used = 0
    for engineer_index, visits in solution.routes.items():
        if not visits:
            continue
        used += 1
        engineer = instance.engineers[engineer_index]
        matrix = instance.distance_km[engineer.transport_id]
        previous = instance.start_node(engineer_index)
        for visit in visits:
            current = instance.request_node(visit.request_index)
            distance += float(matrix[previous, current])
            previous = current
    metrics = {
        ObjectiveCriterion.URGENT_REQUESTS: tiers,
        ObjectiveCriterion.ASSIGNED_REQUESTS: (len(assigned),),
        ObjectiveCriterion.ENGINEERS_USED: (-used,),
        ObjectiveCriterion.TRAVEL_DISTANCE: (-distance,),
    }
    return tuple(
        value
        for criterion in (objective_order or DEFAULT_OBJECTIVE_ORDER)
        for value in metrics[criterion]
    )


async def explain_retry(
    current: np.ndarray, updated: np.ndarray, attempt: int, last_attempt: bool
) -> None:
    """Почему решаем заново: матрица была оптимистичнее расписания, уточняем её и повторяем.

    Плечи между точками R5 оценивает по средней частоте транспорта, а фактический рейс может
    уйти позже. Поэтому замеренные времена возвращаем в матрицу и просим решатель разложить
    заново уже с ними.
    """
    grown = int((updated > current).sum())
    if not grown:
        await run_log.note(
            "Уточнять нечего: замеры совпали с матрицей — снимаем невыполнимые визиты",
            level="warning",
        )
        return
    increase = (updated - current)[updated > current]
    await run_log.note(
        f"Уточняю матрицу: {run_log.plural(grown, 'плечо', 'плеча', 'плеч')} стало дольше, "
        f"больше всего на {int(increase.max())} мин",
        details={"legs": grown, "max_increase_minutes": int(increase.max())},
    )
    await run_log.note(
        "Решаю заново с уточнёнными временами"
        if not last_attempt
        else f"Попытки кончились ({attempt + 1}): последний расчёт идёт без снятых визитов",
    )


async def solve_day(
    loaded: LoadedDay,
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None = None,
    params: SolverParams | None = None,
) -> cuopt_solver.DaySolution:
    """Уточнять только использованные плечи, не пересчитывая полную матрицу R5."""
    params = params or SolverParams()
    if TRANSIT_ID not in loaded.instance.travel_min:
        return await cuopt_solver.solve_day(
            loaded.instance, objective_order=objective_order, ranks=ranks, params=params
        )

    points = node_points(loaded)
    cache: dict[tuple[int, int, int], int] = {}
    instance: ProblemInstance = loaded.instance
    best: cuopt_solver.DaySolution | None = None
    best_score: tuple[float, ...] | None = None
    best_attempt = 0
    for attempt in range(params.transit_attempts):
        await run_log.check_cancelled()
        await run_log.note(
            f"Попытка {attempt + 1} из {params.transit_attempts}: решаю и сверяю с расписанием",
            fraction=attempt / params.transit_attempts,
        )
        solution = await cuopt_solver.solve_day(
            instance, objective_order=objective_order, ranks=ranks, params=params
        )
        last_attempt = attempt + 1 == params.transit_attempts
        checked, observations = await check_schedule(
            loaded, solution, points, cache, skip_infeasible=last_attempt
        )
        if checked is not None:
            score = checked_solution_score(loaded.instance, checked, objective_order, ranks)
            if best_score is not None and best_score > score:
                assert best is not None
                await run_log.note(
                    f"Расписание сходится, но вариант попытки {best_attempt} лучше — сохраняю его"
                )
                return best
            if last_attempt and sum(map(len, checked.routes.values())) < sum(
                map(len, solution.routes.values())
            ):
                await run_log.note("Сохраняю проверенную часть последнего варианта")
            else:
                await run_log.note("Расписание сходится: план принят")
            return checked
        # Даже если статическая матрица ошиблась, оставшаяся часть маршрута может быть
        # выполнима. Сохраняем её до следующего запуска cuOpt: последний вариант не
        # обязан быть лучше предыдущего.
        candidate, _ = await check_schedule(
            loaded, solution, points, cache, skip_infeasible=True, report=False
        )
        assert candidate is not None
        score = checked_solution_score(loaded.instance, candidate, objective_order, ranks)
        assigned = sum(len(visits) for visits in candidate.routes.values())
        if best_score is None or score > best_score:
            best, best_score, best_attempt = candidate, score, attempt + 1
            await run_log.note(
                f"Лучший проверенный вариант: попытка {best_attempt}, назначено {assigned}"
            )
        else:
            await run_log.note(
                f"Проверенный вариант попытки {attempt + 1}: назначено {assigned}, "
                f"лучше остаётся попытка {best_attempt}"
            )
        # Матрицу исходной задачи не меняем: её снимок и другие решатели используют сами.
        updated = instance.travel_min[TRANSIT_ID].copy()
        for (origin, destination), duration in observations.items():
            updated[origin, destination] = max(updated[origin, destination], duration)
        await explain_retry(instance.travel_min[TRANSIT_ID], updated, attempt, False)
        if np.array_equal(updated, instance.travel_min[TRANSIT_ID]):
            assert best is not None
            await run_log.note(
                f"Матрица больше не меняется: сохраняю вариант попытки {best_attempt}"
            )
            return best
        instance = copy.copy(instance)
        instance.travel_min = {**instance.travel_min, TRANSIT_ID: updated}
    raise AssertionError("цикл проверки расписания завершился без результата")
