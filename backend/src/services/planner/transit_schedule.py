"""Проверка маршрутов ОТ по времени фактического выезда между заявками."""

import copy
import logging
import math
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx
import numpy as np

from src.core.errors import ExternalServiceError
from src.schemas.system import SolverParams
from src.schemas.travel import Point, TransportKind
from src.services.planner import cuopt_solver, run_log
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion
from src.services.planner.planner_loader import LoadedDay
from src.services.planner.planner_problem import ProblemInstance
from src.services.travel import build_route, travel_cache

TRANSIT_ID = TransportKind.PUBLIC_TRANSPORT.value
# чем решать задачу дня: cuOpt на видеокарте или OR-Tools на процессоре — вызов одинаковый
Solver = Callable[..., Awaitable[cuopt_solver.DaySolution]]
logger = logging.getLogger(__name__)

# Вставка одного визита меняет время выезда на всех следующих плечах. Проверяем
# ограниченное число наиболее коротких по матрице вариантов, чтобы R5 не выполнял
# тысячи подробных запросов при большом дне. Лимит потом калибруем на реальных днях.
MAX_INSERTION_CHECKS_PER_REQUEST = 24
MAX_INSERTION_CHECKS_PER_PLAN = 120


def node_points(loaded: LoadedDay) -> list[Point]:
    starts = loaded.start_points or [
        Point(latitude=float(e.start_latitude), longitude=float(e.start_longitude))
        for e in loaded.engineers
    ]
    return [
        *starts,
        *(Point(latitude=float(r.latitude), longitude=float(r.longitude)) for r in loaded.requests),
    ]


async def leg_duration(
    loaded: LoadedDay,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    engineer_index: int,
    previous: int,
    next_node: int,
    available: float,
) -> int:
    """Реальное время ОТ в момент выезда; другие режимы используют свою матрицу."""
    engineer = loaded.instance.engineers[engineer_index]
    if engineer.transport_id != TRANSIT_ID:
        return int(loaded.instance.travel_min[engineer.transport_id][previous, next_node])
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
            raise ExternalServiceError(f"R5 не смог проверить расписание плана: {error}") from error
        cache[key] = math.ceil(route.duration_min - 1e-9)
    return cache[key]


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
            duration = await leg_duration(
                loaded, points, cache, engineer_index, previous, next_node, available
            )
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


async def counted_check(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    *,
    skip_infeasible: bool,
) -> tuple[cuopt_solver.DaySolution | None, dict[tuple[int, int], int]]:
    """Проверка расписания и строка журнала: сколько плеч взято из кеша R5, сколько спрошено."""
    with travel_cache.counting() as counters:
        result = await check_schedule(
            loaded, solution, points, cache, skip_infeasible=skip_infeasible
        )
    if counters.from_cache or counters.from_r5:
        await run_log.note(
            f"Плечи проверки: из кеша {counters.from_cache}, запросов к R5 {counters.from_r5}"
        )
    return result


def hhmm(minutes: float) -> str:
    """Минуты от начала дня — в часы и минуты: журнал читают люди."""
    total = int(minutes)
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def checked_solution_score(
    instance: ProblemInstance,
    solution: cuopt_solver.DaySolution,
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None,
    kept_request_ids: set[int] | None = None,
) -> tuple[float, ...]:
    """Сравнить проверенные R5 варианты по той же иерархии, что использует cuOpt.

    Пробег здесь матричный, как в цели cuOpt; точный пробег по маршрутам измеряется позже.
    Первой ступенью идут потерянные заявки яруса B (кто влез в первый расчёт): их выкидывать
    нельзя, поэтому вариант, где такая заявка пропала, проигрывает любому другому
    (docs/algoV2.md, шаг 3).
    """
    assigned = [visit.request_index for visits in solution.routes.values() for visit in visits]
    lost_kept = 0
    if kept_request_ids:
        placed = {instance.requests[index].request_id for index in assigned}
        lost_kept = len(kept_request_ids - placed)
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
    return (
        -lost_kept,
        *(
            value
            for criterion in (objective_order or DEFAULT_OBJECTIVE_ORDER)
            for value in metrics[criterion]
        ),
    )


def insertion_positions(
    instance: ProblemInstance, solution: cuopt_solver.DaySolution, request_index: int
) -> list[tuple[int, int]]:
    """Позиции по приблизительному приросту километров, чередуя подходящие бригады."""
    request_node = instance.request_node(request_index)
    by_engineer: list[list[tuple[float, int, int]]] = []
    for engineer_index in instance.candidates(request_index):
        visits = solution.routes.get(engineer_index, [])
        matrix = instance.distance_km[instance.engineers[engineer_index].transport_id]
        choices = []
        for position in range(len(visits) + 1):
            previous = (
                instance.start_node(engineer_index)
                if position == 0
                else instance.request_node(visits[position - 1].request_index)
            )
            next_node = (
                instance.request_node(visits[position].request_index)
                if position < len(visits)
                else None
            )
            increase = float(matrix[previous, request_node])
            if next_node is not None:
                increase += float(matrix[request_node, next_node] - matrix[previous, next_node])
            choices.append((increase, engineer_index, position))
        by_engineer.append(sorted(choices))

    # Сначала хотя бы один вариант для каждой бригады; затем самые дешёвые оставшиеся
    # позиции независимо от бригады. Так лимит не съедают только первые маршруты.
    first = sorted(choices.pop(0) for choices in by_engineer if choices)
    remaining = sorted(choice for choices in by_engineer for choice in choices)
    return [
        (engineer_index, position)
        for _, engineer_index, position in (first + remaining)[:MAX_INSERTION_CHECKS_PER_REQUEST]
    ]


async def inserted_route(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    engineer_index: int,
    position: int,
    request_index: int,
) -> list[cuopt_solver.PlannedVisit] | None:
    """Проверить новое плечо и весь изменившийся хвост маршрута по времени выезда."""
    instance = loaded.instance
    engineer = instance.engineers[engineer_index]
    existing = solution.routes.get(engineer_index, [])
    prefix = list(existing[:position])
    if prefix:
        last = prefix[-1]
        available = last.work_start_minute + instance.requests[last.request_index].duration_min
        previous = instance.request_node(last.request_index)
    else:
        available = engineer.shift_start_min
        previous = instance.start_node(engineer_index)

    for index in [request_index, *(visit.request_index for visit in existing[position:])]:
        next_node = instance.request_node(index)
        try:
            duration = await leg_duration(
                loaded, points, cache, engineer_index, previous, next_node, available
            )
        except ExternalServiceError as error:
            cause = error.__cause__
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
                return None
            raise
        request = instance.requests[index]
        start = max(available + duration, request.window_start_min)
        if start > request.window_end_min or start + request.duration_min > engineer.shift_end_min:
            return None
        prefix.append(cuopt_solver.PlannedVisit(index, start))
        available = start + request.duration_min
        previous = next_node
    return prefix


async def repair_unassigned(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None,
    kept_request_ids: set[int] | None = None,
) -> cuopt_solver.DaySolution:
    """Довставить заявки без сдвига уже назначенных между бригадами и без нарушения R5.

    Заявки яруса B (влезли в первый расчёт) возвращаем первыми и не считаем их проверки в
    общем лимите: выкидывать их нельзя, поэтому на них вставок не жалеем.
    """
    instance = loaded.instance
    assigned = {visit.request_index for visits in solution.routes.values() for visit in visits}
    pending = set(cuopt_solver.schedulable_request_indices(instance)) - assigned
    if not pending:
        return solution
    kept = kept_request_ids or set()
    ordered = sorted(
        pending,
        key=lambda index: (
            instance.requests[index].request_id not in kept,
            (ranks or {}).get(index, instance.requests[index].objective_rank),
            instance.requests[index].window_end_min,
            instance.requests[index].request_id,
        ),
    )
    await run_log.note(f"Доразмещаю {len(ordered)} неназначенных заявок через R5")
    current = solution
    current_score = checked_solution_score(
        instance, current, objective_order, ranks, kept_request_ids
    )
    checks = 0
    restored = 0
    for request_index in ordered:
        must_keep = instance.requests[request_index].request_id in kept
        winner = None
        winner_score = current_score
        for engineer_index, position in insertion_positions(instance, current, request_index):
            if checks >= MAX_INSERTION_CHECKS_PER_PLAN and not must_keep:
                break
            await run_log.check_cancelled()
            checks += 1
            route = await inserted_route(
                loaded, current, points, cache, engineer_index, position, request_index
            )
            if route is None:
                continue
            candidate = cuopt_solver.DaySolution({**current.routes, engineer_index: route})
            score = checked_solution_score(
                instance, candidate, objective_order, ranks, kept_request_ids
            )
            if score > winner_score:
                winner, winner_score = candidate, score
        if winner is not None:
            current, current_score = winner, winner_score
            restored += 1
            await run_log.note(
                f"№{instance.requests[request_index].request_id} доразмещена; "
                f"назначено {sum(len(route) for route in current.routes.values())}"
            )
        if checks >= MAX_INSERTION_CHECKS_PER_PLAN and not must_keep:
            break
    await run_log.note(
        f"Доразмещение: возвращено {restored} из {len(ordered)}, проверено {checks} вставок",
        details={"restored": restored, "unassigned": len(ordered), "checked": checks},
    )
    return current


async def finish_solution(
    loaded: LoadedDay,
    solution: cuopt_solver.DaySolution,
    points: list[Point],
    cache: dict[tuple[int, int, int], int],
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None,
    kept_request_ids: set[int] | None,
    fallback_solution: cuopt_solver.DaySolution | None,
) -> cuopt_solver.DaySolution:
    """Доразместить заявки и не ухудшить уже проверенный исходный план.

    Обычный результат решателя остаётся первым кандидатом. Если после точной проверки R5
    он потерял прежние назначения, отдельно пытаемся встроить новые окна в маршруты
    исходного плана. Побеждает вариант по той же строгой иерархии, что используется при
    сравнении попыток; поэтому допустимая основа не даст случайно выкинуть старую заявку.
    """
    result = await repair_unassigned(
        loaded, solution, points, cache, objective_order, ranks, kept_request_ids
    )
    if fallback_solution is None:
        return result
    fallback = await repair_unassigned(
        loaded,
        fallback_solution,
        points,
        cache,
        objective_order,
        ranks,
        kept_request_ids,
    )
    result_score = checked_solution_score(
        loaded.instance, result, objective_order, ranks, kept_request_ids
    )
    fallback_score = checked_solution_score(
        loaded.instance, fallback, objective_order, ranks, kept_request_ids
    )
    if fallback_score > result_score:
        await run_log.note(
            "Новый вариант потерял прежние назначения: использую проверенные маршруты "
            "исходного плана и безопасное доразмещение",
            level="warning",
        )
        return fallback
    return result


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
    solve: Solver | None = None,
    kept_request_ids: set[int] | None = None,
    fallback_solution: cuopt_solver.DaySolution | None = None,
) -> cuopt_solver.DaySolution:
    """Уточнять только использованные плечи, не пересчитывая полную матрицу R5.

    kept_request_ids — ярус B второго и третьего расчётов: заявки, которые влезли в первый
    расчёт. Вариант, где такая заявка пропала после проверки расписания, проигрывает любому
    другому, а доразмещение возвращает их первыми (docs/algoV2.md, шаг 3).
    """
    params = params or SolverParams()
    # по умолчанию cuOpt; берём его здесь, а не в значении аргумента, чтобы тесты и вызов
    # с другим решателем видели одну и ту же точку подмены
    solve = solve or cuopt_solver.solve_day
    if TRANSIT_ID not in loaded.instance.travel_min:
        solution = await solve(
            loaded.instance, objective_order=objective_order, ranks=ranks, params=params
        )
        if fallback_solution is None:
            return solution
        points = node_points(loaded)
        cache: dict[tuple[int, int, int], int] = {}
        return await finish_solution(
            loaded,
            solution,
            points,
            cache,
            objective_order,
            ranks,
            kept_request_ids,
            fallback_solution,
        )

    points = node_points(loaded)
    cache = {}
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
        solution = await solve(
            instance, objective_order=objective_order, ranks=ranks, params=params
        )
        last_attempt = attempt + 1 == params.transit_attempts
        checked, observations = await counted_check(
            loaded, solution, points, cache, skip_infeasible=last_attempt
        )
        if checked is not None:
            score = checked_solution_score(
                loaded.instance, checked, objective_order, ranks, kept_request_ids
            )
            if best_score is not None and best_score > score:
                assert best is not None
                await run_log.note(
                    f"Расписание сходится, но вариант попытки {best_attempt} лучше — сохраняю его"
                )
                return await finish_solution(
                    loaded,
                    best,
                    points,
                    cache,
                    objective_order,
                    ranks,
                    kept_request_ids,
                    fallback_solution,
                )
            if last_attempt and sum(map(len, checked.routes.values())) < sum(
                map(len, solution.routes.values())
            ):
                await run_log.note("Сохраняю проверенную часть последнего варианта")
            else:
                await run_log.note("Расписание сходится: план принят")
            return await finish_solution(
                loaded,
                checked,
                points,
                cache,
                objective_order,
                ranks,
                kept_request_ids,
                fallback_solution,
            )
        # Даже если статическая матрица ошиблась, оставшаяся часть маршрута может быть
        # выполнима. Сохраняем её до следующего запуска cuOpt: последний вариант не
        # обязан быть лучше предыдущего.
        candidate, _ = await check_schedule(
            loaded, solution, points, cache, skip_infeasible=True, report=False
        )
        assert candidate is not None
        score = checked_solution_score(
            loaded.instance, candidate, objective_order, ranks, kept_request_ids
        )
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
            return await finish_solution(
                loaded,
                best,
                points,
                cache,
                objective_order,
                ranks,
                kept_request_ids,
                fallback_solution,
            )
        instance = copy.copy(instance)
        instance.travel_min = {**instance.travel_min, TRANSIT_ID: updated}
    raise AssertionError("цикл проверки расписания завершился без результата")
