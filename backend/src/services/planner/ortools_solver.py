"""Решатель маршрутов на процессоре: OR-Tools рядом с cuOpt.

Постановка та же, что у cuOpt (cuopt_solver.build_solver_inputs), поэтому сравнивать планы
можно напрямую: те же матрицы, окна, награды по ярусам, цена бригады и вес пробега.
Отличается только способ поиска — здесь это локальный поиск OR-Tools на процессоре, без
видеокарты. Результат отдаётся тем же DaySolution, что и cuOpt, и дальше идёт общий путь:
проверка расписания по R5, сохранение плана, маршруты.

Как наша задача ложится на OR-Tools:
  - точки — старты бригад и адреса заявок, как в ProblemInstance;
  - маршрут кончается на последней заявке: добавлена фиктивная точка «конец смены», доехать
    до неё стоит 0 (у cuOpt это set_drop_return_trips);
  - «кому можно» — SetAllowedVehiclesForIndex по совместимости из задачи;
  - необязательные заявки — AddDisjunction со штрафом, равным награде за заявку: не взяли
    заявку — потеряли её награду, ровно как в цели cuOpt;
  - цена задействованной бригады — SetFixedCostOfVehicle;
  - окна заявок и смены — измерение времени со слаком (бригада может подождать начала окна).
Цены у OR-Tools целые, поэтому все величины умножаются на COST_SCALE и округляются.
"""

import asyncio
import logging
import math
import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from src.core.errors import ExternalServiceError
from src.schemas.system import SolverParams
from src.services.planner import run_log
from src.services.planner.cuopt_solver import (
    DaySolution,
    PlannedVisit,
    SolverInputs,
    build_solver_inputs,
    describe_model,
    schedulable_request_indices,
    validate_solution,
)
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion
from src.services.planner.planner_problem import ProblemInstance

logger = logging.getLogger(__name__)

# цены у OR-Tools целые: доли награды не должны пропасть при округлении
COST_SCALE = 1000
# сколько минут помещается в смену с запасом: верхняя граница измерения времени
HORIZON_MINUTES = 60 * 48


def _cost(value: float) -> int:
    return round(value * COST_SCALE)


def most_valuable_feasible_order(inputs: SolverInputs) -> int | None:
    """Выбирает лучшую заявку, которую хотя бы одна бригада может выполнить в одиночку.

    Повторный запуск с обязательной заявкой нужен только для режимов, где цена выхода
    бригады делает пустой маршрут формально выгодным. Нельзя просто брать максимальную
    награду: самая ценная заявка может не помещаться в смену, хотя остальные выполнимы.
    """
    feasible: list[int] = []
    for order, location in enumerate(inputs.order_locations):
        service = int(inputs.order_service_minutes[order])
        for vehicle in inputs.order_allowed_vehicles[order]:
            vehicle = int(vehicle)
            transport = int(inputs.vehicle_types[vehicle])
            travel = math.ceil(
                float(
                    inputs.travel_time_matrices[transport][int(inputs.vehicle_locations[vehicle])][
                        int(location)
                    ]
                )
            )
            work_start = max(
                int(inputs.vehicle_shift_start[vehicle]) + travel,
                int(inputs.order_window_start[order]),
            )
            if work_start <= int(inputs.order_window_end[order]) and work_start + service <= int(
                inputs.vehicle_shift_end[vehicle]
            ):
                feasible.append(order)
                break
    if not feasible:
        return None
    return max(feasible, key=lambda order: (float(inputs.order_prizes[order]), -order))


def solve(
    inputs: SolverInputs, time_limit_seconds: float, *, required_order: int | None = None
) -> list[tuple[int, int, float]]:
    """Решает задачу и возвращает визиты: (номер бригады, номер заявки, начало работ).

    required_order — заявка, которую нельзя не взять. Нужна, когда по цене выгоднее не
    выводить никого: пустой план — не ответ (см. solve_day).
    """
    vehicle_count = len(inputs.vehicle_locations)
    order_count = len(inputs.order_locations)
    # последняя точка — фиктивный конец смены: возвращаться на старт не нужно
    end_node = inputs.location_count
    manager = pywrapcp.RoutingIndexManager(
        inputs.location_count + 1,
        vehicle_count,
        [int(node) for node in inputs.vehicle_locations],
        [end_node] * vehicle_count,
    )
    routing = pywrapcp.RoutingModel(manager)

    service_minutes = [0] * (inputs.location_count + 1)
    for order_index, node in enumerate(inputs.order_locations):
        service_minutes[int(node)] = int(inputs.order_service_minutes[order_index])

    # матрицы отдаём целиком: OR-Tools считает по ним сам, без вызова Python на каждое ребро
    # (на дне из 40 заявок это разница между секундами и минутами)
    def cost_matrix(transport_id: int) -> list[list[int]]:
        matrix = inputs.cost_matrices[transport_id]
        weight = inputs.objective.distance_weight
        size = inputs.location_count
        rows = [
            [_cost(weight * float(matrix[origin][destination])) for destination in range(size)]
            + [0]  # доехать до конца смены ничего не стоит
            for origin in range(size)
        ]
        return [*rows, [0] * (size + 1)]

    def time_matrix(transport_id: int) -> list[list[int]]:
        matrix = inputs.travel_time_matrices[transport_id]
        size = inputs.location_count
        rows = [
            [
                service_minutes[origin] + math.ceil(float(matrix[origin][destination]))
                for destination in range(size)
            ]
            # до конца смены доезжать не надо: считается только работа на месте
            + [service_minutes[origin]]
            for origin in range(size)
        ]
        return [*rows, [0] * (size + 1)]

    # у каждого вида транспорта свои матрицы: и цена переезда, и время в пути
    distance_indices, time_indices = {}, {}
    for transport_id in inputs.cost_matrices:
        distance_indices[transport_id] = routing.RegisterTransitMatrix(cost_matrix(transport_id))
        time_indices[transport_id] = routing.RegisterTransitMatrix(time_matrix(transport_id))
    for vehicle in range(vehicle_count):
        transport_id = int(inputs.vehicle_types[vehicle])
        routing.SetArcCostEvaluatorOfVehicle(distance_indices[transport_id], vehicle)
        routing.SetFixedCostOfVehicle(_cost(inputs.objective.vehicle_cost), vehicle)

    routing.AddDimensionWithVehicleTransits(
        [time_indices[int(transport)] for transport in inputs.vehicle_types],
        HORIZON_MINUTES,  # бригада может приехать раньше и подождать начала окна
        HORIZON_MINUTES,
        False,  # смена начинается не в нуле: время начала задаётся окном старта
        "Время",
    )
    time_dimension = routing.GetDimensionOrDie("Время")

    for order_index in range(order_count):
        index = manager.NodeToIndex(int(inputs.order_locations[order_index]))
        time_dimension.CumulVar(index).SetRange(
            int(inputs.order_window_start[order_index]), int(inputs.order_window_end[order_index])
        )
        # заявку можно не брать: тогда теряется её награда — это и есть ярусы из algoV2
        if order_index != required_order:
            routing.AddDisjunction([index], _cost(float(inputs.order_prizes[order_index])))
        allowed = [int(vehicle) for vehicle in inputs.order_allowed_vehicles[order_index]]
        routing.SetAllowedVehiclesForIndex(allowed, index)

    for vehicle in range(vehicle_count):
        shift_start = int(inputs.vehicle_shift_start[vehicle])
        shift_end = int(inputs.vehicle_shift_end[vehicle])
        time_dimension.CumulVar(routing.Start(vehicle)).SetRange(shift_start, shift_end)
        # работа последней заявки должна закончиться до конца смены
        time_dimension.CumulVar(routing.End(vehicle)).SetRange(shift_start, shift_end)
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(vehicle)))

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search.time_limit.FromMilliseconds(int(time_limit_seconds * 1000))
    search.log_search = inputs.params.verbose_log

    started_at = time.perf_counter()
    assignment = routing.SolveWithParameters(search)
    elapsed_seconds = time.perf_counter() - started_at
    if assignment is None:
        if required_order is not None:
            # обязательную заявку выполнить нельзя: значит, день и правда пустой
            return []
        raise ExternalServiceError("OR-Tools не нашёл решение: задача оказалась неразрешимой")

    node_to_order = {int(node): order for order, node in enumerate(inputs.order_locations)}
    visits: list[tuple[int, int, float]] = []
    used_vehicles = 0
    for vehicle in range(vehicle_count):
        index = routing.Start(vehicle)
        visited = False
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            order_index = node_to_order.get(node)
            if order_index is not None:
                visits.append(
                    (vehicle, order_index, float(assignment.Min(time_dimension.CumulVar(index))))
                )
                visited = True
            index = assignment.Value(routing.NextVar(index))
        used_vehicles += int(visited)

    logger.info(
        "решение за %.1f с (лимит %.0f с), бригад %d, цель %.6g",
        elapsed_seconds,
        time_limit_seconds,
        used_vehicles,
        assignment.ObjectiveValue() / COST_SCALE,
    )
    return visits


async def solve_day(
    instance: ProblemInstance,
    *,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    ranks: dict[int, int] | None = None,
    params: SolverParams | None = None,
) -> DaySolution:
    """Тот же вход и выход, что у cuopt_solver.solve_day, но поиск идёт на процессоре."""
    task_request_indices = schedulable_request_indices(instance)
    if not task_request_indices or instance.n_engineers == 0:
        return DaySolution()

    params = params or SolverParams()
    inputs = build_solver_inputs(
        instance,
        task_request_indices,
        distance_weight=params.distance_weight,
        objective_order=objective_order,
        ranks=ranks,
        params=params,
    )
    await describe_model(instance, inputs, task_request_indices, objective_order, ranks)
    try:
        # поиск занимает секунды и держит поток: считаем в отдельном, как и cuOpt
        solving = asyncio.create_task(asyncio.to_thread(solve, inputs, inputs.time_limit_seconds))
        visits = await run_log.wait_cancellable(solving)
        if not visits:
            # пустой план — не ответ: при «меньше бригад важнее заявок» цена бригады выше
            # награды, и по формуле дешевле всего не выводить никого. cuOpt так тоже не делает.
            # Обязываем взять самую ценную заявку, а сколько бригад для этого вывести —
            # решатель выберет сам
            required = most_valuable_feasible_order(inputs)
            if required is not None:
                await run_log.note(
                    "OR-Tools: по цене выгоднее никого не выводить — считаю ещё раз, "
                    "сделав самую ценную выполнимую заявку обязательной"
                )
                solving = asyncio.create_task(
                    asyncio.to_thread(
                        solve, inputs, inputs.time_limit_seconds, required_order=required
                    )
                )
                visits = await run_log.wait_cancellable(solving)
    except ExternalServiceError:
        raise
    except (RuntimeError, ValueError, KeyError, IndexError, OSError) as error:
        logger.exception("Ошибка выполнения OR-Tools")
        raise ExternalServiceError(
            "Не удалось выполнить расчёт OR-Tools; подробности в журнале backend"
        ) from error

    solution = DaySolution()
    for vehicle, order_index, work_start_minute in visits:
        solution.routes.setdefault(vehicle, []).append(
            PlannedVisit(task_request_indices[order_index], work_start_minute)
        )
    for visits_of_vehicle in solution.routes.values():
        visits_of_vehicle.sort(key=lambda visit: visit.work_start_minute)
    assigned = sum(len(route) for route in solution.routes.values())
    await run_log.note(
        f"OR-Tools вернул: назначено {assigned} из {len(task_request_indices)}, "
        f"задействовано {run_log.plural(len(solution.routes), 'бригада', 'бригады', 'бригад')}",
        details={"assigned": assigned, "vehicles": len(solution.routes)},
    )
    validate_solution(instance, solution)
    return solution
