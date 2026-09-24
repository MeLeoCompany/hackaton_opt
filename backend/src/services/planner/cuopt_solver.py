"""Решение задачи дня в cuOpt через Python SDK: ProblemInstance -> routing.DataModel -> маршруты.

Как наша задача ложится на модель cuOpt:
  исполнитель          -> vehicle: старт в его точке, возврата нет, окно = смена, тип = транспорт
  заявка               -> order: окно, длительность работы, динамический prize
  навык и транспорт    -> order_vehicle_match: кому из исполнителей заявку вообще можно отдать
  километры            -> нормализованная cost-матрица: последний уровень оптимизации
  минуты в пути        -> матрица времени в пути: по ней проверяется, что всё успеваем
  неназначенная заявка -> недополученный prize

Заявки, которые не подходят ни одному исполнителю, в cuOpt не отправляются.

Решатель считает на видеокарте NVIDIA прямо в процессе бэкенда. Пакет cuopt-cu13 ставится
с https://pypi.nvidia.com и импортируется только при решении, поэтому остальной бэкенд
и тесты сборки задачи работают и без него.
"""

import asyncio
import logging
import math
import time
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from src.core.errors import ExternalServiceError
from src.schemas.system import SolverParams
from src.services.planner import run_log
from src.services.planner.objective_policy import (
    DEFAULT_OBJECTIVE_ORDER,
    ObjectiveCriterion,
    validate_objective_order,
)
from src.services.planner.planner_problem import (
    RANK_EMERGENCY,
    RANK_HIGH,
    RANK_MOVED_HIGH,
    RANK_MOVED_NORMAL,
    RANK_NORMAL,
    RANK_PROMISED,
    ProblemInstance,
)

# ярусы заявок словами — для журнала расчёта (docs/algoV2.md)
RANK_NAMES = {
    RANK_EMERGENCY: "аварийные",
    RANK_PROMISED: "согласовано с клиентом",
    RANK_MOVED_HIGH: "перенесённые P2",
    RANK_MOVED_NORMAL: "перенесённые P3",
    RANK_HIGH: "высокий приоритет",
    RANK_NORMAL: "обычные",
}

# Objective cuOpt хранится в float32. Ограничиваем суммарный масштаб половиной точного
# целочисленного диапазона: остаётся запас для сложения и единичных границ Big-M.
# Более крупной задаче нужен многоэтапный solve, а не потеря иерархии из-за округления.
FLOAT32_SAFE_OBJECTIVE = 2**23

TIME_LIMIT_PER_LOCATION_SECONDS = 0.2
ADAPTIVE_TIME_FREE_LOCATIONS = 20


@dataclass
class PlannedVisit:
    request_index: int
    # минуты от начала дня: момент начала работ (если приехал раньше окна, это время открытия окна)
    work_start_minute: float


@dataclass
class DaySolution:
    # номер исполнителя в задаче -> его визиты по порядку объезда
    routes: dict[int, list[PlannedVisit]] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectivePolicy:
    """Коэффициенты строгой иерархии выбранных диспетчером критериев."""

    criteria: tuple[ObjectiveCriterion, ...]
    # награда за выполненную заявку по ярусу (planner_problem.RANK_*): авария, обещание,
    # перенос, приоритет. Самый нижний ярус отдельной ступени не получает — ему regular_reward
    rank_rewards: dict[int, float]
    regular_reward: float

    def reward_for(self, rank: int) -> float:
        return self.rank_rewards.get(rank, self.regular_reward)

    vehicle_cost: float
    distance_weight: float
    distance_scale: float


@dataclass
class SolverInputs:
    """Всё, что загружается в DataModel, — массивами numpy в тех типах, которые ждёт cuOpt.

    Номер исполнителя здесь = номер vehicle в cuOpt, номер заявки в списке = номер order.
    """

    location_count: int
    cost_matrices: dict[int, np.ndarray]  # нормализованная цена переездов, float32
    travel_time_matrices: dict[int, np.ndarray]  # тип транспорта -> минуты в пути, float32
    vehicle_locations: np.ndarray  # int32: стартовая точка каждого исполнителя
    vehicle_types: np.ndarray  # uint8: тип транспорта исполнителя
    vehicle_shift_start: np.ndarray  # int32
    vehicle_shift_end: np.ndarray  # int32
    vehicle_fixed_costs: np.ndarray  # float32
    order_locations: np.ndarray  # int32: точка заявки
    order_window_start: np.ndarray  # int32
    order_window_end: np.ndarray  # int32
    order_service_minutes: np.ndarray  # int32: длительность работы
    order_prizes: np.ndarray  # float32
    order_allowed_vehicles: list[np.ndarray]  # int32: кому из исполнителей можно отдать заявку
    # тип оборудования -> (расход каждой заявки, запас каждой бригады)
    equipment_dimensions: dict[int, tuple[np.ndarray, np.ndarray]]
    objective: ObjectivePolicy
    # параметры расчёта: сколько искать решение и подробно ли писать лог решателя
    params: SolverParams = field(default_factory=SolverParams)

    @property
    def time_limit_seconds(self) -> float:
        """Маленькой задаче хватает базового лимита; дальше добавляется время на поиск."""
        return self.params.limit_for(self.location_count)


async def solve_day(
    instance: ProblemInstance,
    *,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    ranks: dict[int, int] | None = None,
    params: SolverParams | None = None,
) -> DaySolution:
    """ranks — ярус каждой заявки по номеру в instance.requests; нет — берётся из самой заявки
    (objective_rank). Второй расчёт при синхронизации передаёт свои ярусы (docs/algoV2.md)."""
    task_request_indices = schedulable_request_indices(instance)
    if not task_request_indices or instance.n_engineers == 0:
        return DaySolution()

    # решение занимает секунды — считаем в отдельном потоке, чтобы не блокировать остальные запросы
    try:
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
        solving = asyncio.create_task(
            asyncio.to_thread(run_cuopt, inputs, inputs.time_limit_seconds)
        )
        route_records = await run_log.wait_cancellable(solving)
        solution = parse_route_records(route_records, task_request_indices)
        assigned = sum(len(visits) for visits in solution.routes.values())
        await run_log.note(
            f"cuOpt вернул: назначено {assigned} из {len(task_request_indices)}, "
            f"задействовано {run_log.plural(len(solution.routes), 'бригада', 'бригады', 'бригад')}",
            details={"assigned": assigned, "vehicles": len(solution.routes)},
        )
    except ExternalServiceError:
        raise
    except (RuntimeError, ValueError, KeyError, IndexError, OSError) as error:
        logging.getLogger(__name__).exception("Ошибка выполнения cuOpt")
        raise ExternalServiceError(
            "Не удалось выполнить расчёт cuOpt; подробности в журнале backend"
        ) from error
    validate_solution(instance, solution)
    return solution


def schedulable_request_indices(instance: ProblemInstance) -> list[int]:
    """Заявки, которые подходят хотя бы одному исполнителю, — только их отправляем в cuOpt."""
    return [
        request_index
        for request_index in range(instance.n_requests)
        if instance.compatible[request_index].any()
        and instance.requests[request_index].window_start_min
        <= instance.requests[request_index].window_end_min
    ]


def build_solver_inputs(
    instance: ProblemInstance,
    task_request_indices: list[int],
    *,
    distance_weight: float | None = None,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    ranks: dict[int, int] | None = None,
    params: SolverParams | None = None,
) -> SolverInputs:
    """ProblemInstance -> массивы для DataModel. task_request_indices — какие заявки отправляем."""
    transport_ids = sorted({engineer.transport_id for engineer in instance.engineers})
    _validate_transport_matrices(instance, transport_ids)
    engineers = instance.engineers
    requests = [instance.requests[request_index] for request_index in task_request_indices]
    selected_nodes = np.array(
        [instance.start_node(index) for index in range(instance.n_engineers)]
        + [instance.request_node(index) for index in task_request_indices],
        dtype=np.int32,
    )
    request_ranks = rank_by_index(instance, task_request_indices, ranks)
    objective = build_objective_policy(
        instance,
        task_request_indices,
        (params or SolverParams()).distance_weight if distance_weight is None else distance_weight,
        objective_order,
        request_ranks,
    )
    equipment_ids = sorted(
        {
            equipment_id
            for request in requests
            for equipment_id in request.equipment_demand
        }
    )

    return SolverInputs(
        location_count=len(selected_nodes),
        cost_matrices={
            transport_id: (
                instance.distance_km[transport_id][np.ix_(selected_nodes, selected_nodes)]
                / objective.distance_scale
            ).astype(np.float32)
            for transport_id in transport_ids
        },
        travel_time_matrices={
            transport_id: instance.travel_min[transport_id][
                np.ix_(selected_nodes, selected_nodes)
            ].astype(np.float32)
            for transport_id in transport_ids
        },
        vehicle_locations=np.array(
            [instance.start_node(engineer_index) for engineer_index in range(instance.n_engineers)],
            dtype=np.int32,
        ),
        vehicle_types=np.array([engineer.transport_id for engineer in engineers], dtype=np.uint8),
        vehicle_shift_start=np.array(
            [engineer.shift_start_min for engineer in engineers], dtype=np.int32
        ),
        vehicle_shift_end=np.array(
            [engineer.shift_end_min for engineer in engineers], dtype=np.int32
        ),
        vehicle_fixed_costs=np.full(instance.n_engineers, objective.vehicle_cost, dtype=np.float32),
        order_locations=np.array(
            [instance.n_engineers + index for index in range(len(task_request_indices))],
            dtype=np.int32,
        ),
        order_window_start=np.array(
            [request.window_start_min for request in requests], dtype=np.int32
        ),
        order_window_end=np.array([request.window_end_min for request in requests], dtype=np.int32),
        order_service_minutes=np.array(
            [request.duration_min for request in requests], dtype=np.int32
        ),
        order_prizes=np.array(
            [objective.reward_for(request_ranks[index]) for index in task_request_indices],
            dtype=np.float32,
        ),
        order_allowed_vehicles=[
            np.array(instance.candidates(request_index), dtype=np.int32)
            for request_index in task_request_indices
        ],
        equipment_dimensions={
            equipment_id: (
                np.array(
                    [request.equipment_demand.get(equipment_id, 0) for request in requests],
                    dtype=np.int32,
                ),
                np.array(
                    [
                        engineer.equipment_capacity.get(equipment_id, 0)
                        for engineer in engineers
                    ],
                    dtype=np.int32,
                ),
            )
            for equipment_id in equipment_ids
        },
        objective=objective,
        params=params or SolverParams(),
    )


def _validate_transport_matrices(instance: ProblemInstance, transport_ids: list[int]) -> None:
    """Не передавать в cuOpt матрицы с повреждённой размерностью или значениями."""
    size = instance.n_engineers + instance.n_requests
    for transport_id in transport_ids:
        for name, matrices in (
            ("расстояний", instance.distance_km),
            ("времени", instance.travel_min),
        ):
            matrix = matrices.get(transport_id)
            if matrix is None or matrix.shape != (size, size):
                raise ValueError(
                    f"матрица {name} для транспорта {transport_id} имеет неверный размер"
                )
            if not np.isfinite(matrix).all() or np.any(matrix < 0):
                raise ValueError(
                    f"матрица {name} для транспорта {transport_id} содержит недопустимые значения"
                )
            if np.any(matrix > np.finfo(np.float32).max):
                raise ValueError(
                    f"матрица {name} для транспорта {transport_id} превышает диапазон float32"
                )


def rank_by_index(
    instance: ProblemInstance,
    task_request_indices: list[int],
    ranks: dict[int, int] | None,
) -> dict[int, int]:
    """Ярус каждой заявки: переданный снаружи или её собственный."""
    return {
        index: (ranks or {}).get(index, instance.requests[index].objective_rank)
        for index in task_request_indices
    }


def build_objective_policy(
    instance: ProblemInstance,
    task_request_indices: list[int],
    distance_weight: float,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
    ranks: dict[int, int] | None = None,
) -> ObjectivePolicy:
    """Строит безопасные Big-M коэффициенты для выбранной строгой иерархии.

    Каждый коэффициент больше максимально возможного вклада всех нижних уровней.
    Cost-матрицы нормализованы, поэтому диапазон общего пробега не превышает единицу.
    """
    if not math.isfinite(distance_weight) or distance_weight <= 0:
        raise ValueError("вес пробега cuOpt должен быть конечным положительным числом")

    criteria = validate_objective_order(objective_order)

    request_count = len(task_request_indices)
    request_ranks = rank_by_index(instance, task_request_indices, ranks)
    rank_counts = Counter(request_ranks.values())
    # самый нижний ярус — базовый: отдельной ступени ему не нужно, он получает assigned_reward
    tier_ranks = sorted(rank_counts)[:-1] if rank_counts else []
    maximum_changes = {
        ObjectiveCriterion.ASSIGNED_REQUESTS: request_count,
        ObjectiveCriterion.ENGINEERS_USED: instance.n_engineers,
        ObjectiveCriterion.TRAVEL_DISTANCE: 1.0,
    }
    # «срочность» — это ступени по уровням приоритета: сначала аварии, потом подключения.
    # Каждая ступень сильнее всех нижних вместе взятых, поэтому одна авария важнее любого
    # числа подключений, а подключение — любого числа обычных заявок
    tiers: list[tuple[object, float]] = []
    for criterion in criteria:
        if criterion is ObjectiveCriterion.URGENT_REQUESTS:
            tiers += [(("rank", rank), rank_counts[rank]) for rank in tier_ranks]
        else:
            tiers.append((criterion, maximum_changes[criterion]))

    coefficients: dict[object, float] = {}
    lower_levels = 0.0
    for key, maximum in reversed(tiers):
        increment = distance_weight if key is ObjectiveCriterion.TRAVEL_DISTANCE else 1.0
        coefficient = lower_levels + increment
        coefficients[key] = coefficient
        lower_levels += maximum * coefficient

    assigned_reward = coefficients[ObjectiveCriterion.ASSIGNED_REQUESTS]
    rank_rewards = {rank: assigned_reward + coefficients[("rank", rank)] for rank in tier_ranks}
    urgent_reward = rank_rewards.get(RANK_EMERGENCY, assigned_reward)
    vehicle_cost = coefficients[ObjectiveCriterion.ENGINEERS_USED]
    effective_distance_weight = coefficients[ObjectiveCriterion.TRAVEL_DISTANCE]
    maximum_objective_magnitude = lower_levels
    coefficient_values = (
        vehicle_cost,
        assigned_reward,
        urgent_reward,
        effective_distance_weight,
        maximum_objective_magnitude,
    )
    if not all(math.isfinite(value) for value in coefficient_values):
        raise ValueError("коэффициенты целевой функции cuOpt вышли за допустимый диапазон")
    if maximum_objective_magnitude > FLOAT32_SAFE_OBJECTIVE:
        raise ValueError(
            "задача слишком велика для безопасной одноэтапной float32 objective cuOpt; "
            "нужен многоэтапный расчёт"
        )

    if any(
        not np.isfinite(matrix).all() or np.any(matrix < 0)
        for matrix in instance.distance_km.values()
    ):
        raise ValueError("матрица расстояний содержит недопустимые значения")

    # Исключаем заведомо непроходимые sentinel-пары: одно плечо не может занимать
    # больше самой длинной смены. Иначе 100_000 км раздули бы scale и съели точность
    # реальных московских расстояний.
    max_shift_span = max(
        (engineer.shift_end_min - engineer.shift_start_min for engineer in instance.engineers),
        default=0,
    )
    selected_nodes = np.array(
        [instance.start_node(index) for index in range(instance.n_engineers)]
        + [instance.request_node(index) for index in task_request_indices],
        dtype=np.int32,
    )
    feasible_arc_distances = []
    for transport_id, distance_matrix in instance.distance_km.items():
        distance_matrix = distance_matrix[np.ix_(selected_nodes, selected_nodes)]
        travel_matrix = instance.travel_min[transport_id][np.ix_(selected_nodes, selected_nodes)]
        feasible = (
            np.isfinite(travel_matrix) & (travel_matrix >= 0) & (travel_matrix <= max_shift_span)
        )
        if feasible.any():
            feasible_arc_distances.append(float(np.max(distance_matrix[feasible])))
    max_arc_distance = max(feasible_arc_distances, default=0.0)

    # Без возврата в депо у каждой выполненной заявки ровно одно входящее плечо.
    distance_scale = max(request_count * max_arc_distance, 1.0)
    if not math.isfinite(distance_scale):
        raise ValueError("масштаб расстояний cuOpt вышел за допустимый диапазон")

    return ObjectivePolicy(
        criteria=criteria,
        rank_rewards=rank_rewards,
        regular_reward=assigned_reward,
        vehicle_cost=vehicle_cost,
        distance_weight=effective_distance_weight,
        distance_scale=distance_scale,
    )


def run_cuopt(inputs: SolverInputs, time_limit_seconds: float) -> list[dict]:
    """Загружает задачу в DataModel, решает и возвращает таблицу маршрутов строками."""
    try:
        from cuopt import routing  # type: ignore[import-untyped]
    except ImportError as error:
        raise ExternalServiceError(
            "Решатель cuOpt не установлен: pip install cuopt-cu13 --extra-index-url https://pypi.nvidia.com"
        ) from error

    vehicle_count = len(inputs.vehicle_locations)
    order_count = len(inputs.order_locations)
    data_model = routing.DataModel(inputs.location_count, vehicle_count, order_count)

    for transport_id, cost_matrix in inputs.cost_matrices.items():
        data_model.add_cost_matrix(cost_matrix, transport_id)
    for transport_id, travel_time_matrix in inputs.travel_time_matrices.items():
        data_model.add_transit_time_matrix(travel_time_matrix, transport_id)

    # исполнители
    data_model.set_vehicle_types(inputs.vehicle_types)
    data_model.set_vehicle_locations(inputs.vehicle_locations, inputs.vehicle_locations)
    data_model.set_vehicle_time_windows(inputs.vehicle_shift_start, inputs.vehicle_shift_end)
    # маршрут заканчивается на последней заявке, возврат в старт не нужен (ТЗ 2.4)
    data_model.set_drop_return_trips(np.ones(vehicle_count, dtype=bool))
    data_model.set_vehicle_fixed_costs(inputs.vehicle_fixed_costs)

    # заявки
    data_model.set_order_locations(inputs.order_locations)
    data_model.set_order_time_windows(inputs.order_window_start, inputs.order_window_end)
    data_model.set_order_service_times(inputs.order_service_minutes)
    # приз за заявку разрешает решателю оставить невыполнимую заявку неназначенной,
    # а не объявлять неразрешимой всю задачу
    data_model.set_order_prizes(inputs.order_prizes)
    for order_index, allowed_vehicles in enumerate(inputs.order_allowed_vehicles):
        data_model.add_order_vehicle_match(order_index, allowed_vehicles)
    for equipment_id, (demand, capacity) in inputs.equipment_dimensions.items():
        data_model.add_capacity_dimension(f"equipment_{equipment_id}", demand, capacity)

    data_model.set_objective_function(
        np.array(
            [
                int(routing.Objective.PRIZE),
                int(routing.Objective.VEHICLE_FIXED_COST),
                int(routing.Objective.COST),
            ],
            dtype=np.int32,
        ),
        np.array([1.0, 1.0, inputs.objective.distance_weight], dtype=np.float32),
    )

    solver_settings = routing.SolverSettings()
    solver_settings.set_time_limit(time_limit_seconds)
    if inputs.params.verbose_log:
        # подробный вывод решателя: нужен, когда разбираются, почему план именно такой
        solver_settings.set_verbose_mode(True)
    started_at = time.perf_counter()
    assignment = routing.Solve(data_model, solver_settings)
    elapsed_seconds = time.perf_counter() - started_at

    if assignment.get_status() != routing.SolutionStatus.SUCCESS.value:
        message = assignment.get_error_message() or assignment.get_message()
        raise ExternalServiceError(
            f"cuOpt не нашёл решение: статус {assignment.get_status()}, {message}"
        )
    # строка уходит в журнал расчёта, поэтому пишем её по-человечески, без служебных enum
    logging.getLogger(__name__).info(
        "решение за %.1f с (лимит %.0f с), бригад %d, цель %.6g; %s",
        elapsed_seconds,
        time_limit_seconds,
        assignment.get_vehicle_count(),
        assignment.get_total_objective(),
        objective_parts(assignment.get_objective_values()),
    )
    return assignment.get_route().to_pandas().to_dict("records")


def objective_parts(values: dict) -> str:
    """Составляющие цели cuOpt словами: из чего сложилась итоговая оценка решения."""
    names = {"PRIZE": "за заявки", "VEHICLE_FIXED_COST": "за бригады", "COST": "за пробег"}
    parts = [
        f"{names.get(getattr(key, 'name', str(key)), getattr(key, 'name', key))} {value:.4g}"
        for key, value in values.items()
    ]
    return ", ".join(parts)


async def describe_model(
    instance: ProblemInstance,
    inputs: SolverInputs,
    task_request_indices: list[int],
    objective_order: tuple[ObjectiveCriterion, ...],
    ranks: dict[int, int] | None,
) -> None:
    """Пишет в журнал параметры задачи: по ним видно, что именно решает cuOpt.

    Без этого при долгом расчёте непонятно, большая ли задача, какие у неё ярусы и во что
    превратился выбранный порядок целей.
    """
    request_ranks = rank_by_index(instance, task_request_indices, ranks)
    by_rank = Counter(request_ranks.values())
    tiers = ", ".join(
        f"{RANK_NAMES.get(rank, rank)} — {count}" for rank, count in sorted(by_rank.items())
    )
    windows = [
        instance.requests[index].window_end_min - instance.requests[index].window_start_min
        for index in task_request_indices
    ]
    work = sum(instance.requests[index].duration_min for index in task_request_indices)
    shifts = sum(
        engineer.shift_end_min - engineer.shift_start_min for engineer in instance.engineers
    )
    await run_log.note(
        f"Задача: {run_log.plural(len(task_request_indices), 'заявка', 'заявки', 'заявок')}, "
        f"{run_log.plural(instance.n_engineers, 'бригада', 'бригады', 'бригад')}, "
        f"{run_log.plural(inputs.location_count, 'точка', 'точки', 'точек')}, "
        f"лимит решателя {inputs.time_limit_seconds:.0f} c",
        details={
            "orders": len(task_request_indices),
            "vehicles": instance.n_engineers,
            "locations": inputs.location_count,
            "time_limit_seconds": round(inputs.time_limit_seconds, 1),
        },
    )
    await run_log.note(f"Ярусы заявок: {tiers}", details={"tiers": dict(by_rank)})
    await run_log.note(
        f"Работы на {work // 60} ч {work % 60} мин при сменах на {shifts // 60} ч, "
        f"окно заявки в среднем {round(sum(windows) / max(len(windows), 1))} мин",
        details={"work_minutes": work, "shift_minutes": shifts},
    )
    params = inputs.params
    await run_log.note(
        f"Параметры расчёта: время поиска {params.time_limit_seconds:g}–"
        f"{params.max_time_limit_seconds:g} c (+{params.seconds_per_location:g} c на точку "
        f"сверх {params.free_locations}), вес пробега {params.distance_weight:g}, "
        f"попыток по расписанию {params.transit_attempts}",
        details=params.model_dump(),
    )
    await run_log.note(
        "Порядок целей: " + " → ".join(criterion.value for criterion in objective_order),
        details={"objective_order": [criterion.value for criterion in objective_order]},
    )
    objective = inputs.objective
    # веса ярусов — это и есть «под капотом» algoV2: у каждой ступени награда больше суммы нижних
    rewards = ", ".join(
        f"{RANK_NAMES.get(rank, rank)} {reward:.3g}"
        for rank, reward in sorted(objective.rank_rewards.items())
    )
    await run_log.note(
        f"Награды: {rewards + ', ' if rewards else ''}обычная заявка "
        f"{objective.regular_reward:.3g}; цена бригады {objective.vehicle_cost:.3g}, "
        f"вес пробега {objective.distance_weight:.3g}",
        details={
            "rank_rewards": {str(rank): value for rank, value in objective.rank_rewards.items()},
            "regular_reward": objective.regular_reward,
            "vehicle_cost": objective.vehicle_cost,
            "distance_weight": objective.distance_weight,
        },
    )


def parse_route_records(route_records: list[dict], task_request_indices: list[int]) -> DaySolution:
    """Таблица маршрутов cuOpt -> визиты по исполнителям в порядке объезда.

    Каждая строка — одна остановка: truck_id (номер исполнителя), route (номер заявки
    в списке отправленных), arrival_stamp (время начала работ в минутах от начала дня),
    location (номер точки), type (Depot — старт, Delivery — заявка).
    Строки одного исполнителя идут по порядку объезда.
    """
    solution = DaySolution()
    for record in route_records:
        if record["type"] != "Delivery":
            continue
        engineer_index = int(record["truck_id"])
        visit = PlannedVisit(
            request_index=task_request_indices[int(record["route"])],
            work_start_minute=float(record["arrival_stamp"]),
        )
        solution.routes.setdefault(engineer_index, []).append(visit)
    return solution


def validate_solution(instance: ProblemInstance, solution: DaySolution) -> None:
    """Reject invalid solver output before persisting a plan."""
    seen = set()
    for engineer_index, visits in solution.routes.items():
        if not 0 <= engineer_index < instance.n_engineers:
            raise ExternalServiceError("Решатель вернул неизвестного исполнителя")
        engineer = instance.engineers[engineer_index]
        if any(not 0 <= visit.request_index < instance.n_requests for visit in visits):
            raise ExternalServiceError("Решатель вернул неизвестную или повторную заявку")
        if not instance.route_fits_equipment(
            engineer_index, [visit.request_index for visit in visits]
        ):
            raise ExternalServiceError("Результат решателя превышает запас оборудования бригады")
        previous_node = instance.start_node(engineer_index)
        available: float = engineer.shift_start_min
        for visit in visits:
            index = visit.request_index
            if not 0 <= index < instance.n_requests or index in seen:
                raise ExternalServiceError("Решатель вернул неизвестную или повторную заявку")
            seen.add(index)
            request = instance.requests[index]
            start = visit.work_start_minute
            arrival = (
                available
                + instance.travel_min[engineer.transport_id][
                    previous_node, instance.request_node(index)
                ]
            )
            if (
                not math.isfinite(start)
                or not instance.compatible[index, engineer_index]
                or start < max(arrival, request.window_start_min) - 1e-4
                or start > request.window_end_min + 1e-4
                or start + request.duration_min > engineer.shift_end_min + 1e-4
            ):
                raise ExternalServiceError(
                    "Результат решателя нарушает ограничения заявки или смены"
                )
            available = start + request.duration_min
            previous_node = instance.request_node(index)
