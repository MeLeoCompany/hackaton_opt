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
from dataclasses import dataclass, field

import numpy as np

from src.core.config import settings
from src.core.errors import ExternalServiceError
from src.services.planner.planner_problem import ProblemInstance

# Objective cuOpt хранится в float32. Ограничиваем суммарный масштаб половиной точного
# целочисленного диапазона: остаётся запас для сложения и единичных границ Big-M.
# Более крупной задаче нужен многоэтапный solve, а не потеря иерархии из-за округления.
FLOAT32_SAFE_OBJECTIVE = 2**23

SOLVE_SUCCESS = 0


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
    """Динамические коэффициенты строгой иерархии целевой функции.

    Любая срочная заявка важнее всех обычных и нижних уровней вместе; одна обычная
    важнее всех исполнителей и пробега; один исполнитель важнее любой разницы пробега.
    """

    urgent_reward: float
    regular_reward: float
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
    objective: ObjectivePolicy


async def solve_day(instance: ProblemInstance) -> DaySolution:
    task_request_indices = schedulable_request_indices(instance)
    if not task_request_indices or instance.n_engineers == 0:
        return DaySolution()

    # решение занимает секунды — считаем в отдельном потоке, чтобы не блокировать остальные запросы
    try:
        inputs = build_solver_inputs(
            instance, task_request_indices, distance_weight=settings.cuopt_distance_weight
        )
        route_records = await asyncio.to_thread(run_cuopt, inputs, settings.cuopt_time_limit_seconds)
        solution = parse_route_records(route_records, task_request_indices)
    except ExternalServiceError:
        raise
    except (RuntimeError, ValueError, KeyError, IndexError, OSError) as error:
        logging.getLogger(__name__).exception("Ошибка выполнения cuOpt")
        raise ExternalServiceError("Не удалось выполнить расчёт cuOpt; подробности в журнале backend") from error
    validate_solution(instance, solution)
    return solution


def schedulable_request_indices(instance: ProblemInstance) -> list[int]:
    """Заявки, которые подходят хотя бы одному исполнителю, — только их отправляем в cuOpt."""
    return [
        request_index
        for request_index in range(instance.n_requests)
        if instance.compatible[request_index].any()
        and instance.requests[request_index].window_start_min <= instance.requests[request_index].window_end_min
    ]


def build_solver_inputs(
    instance: ProblemInstance,
    task_request_indices: list[int],
    *,
    distance_weight: float | None = None,
) -> SolverInputs:
    """ProblemInstance -> массивы для DataModel. task_request_indices — какие заявки отправляем."""
    transport_ids = sorted({engineer.transport_id for engineer in instance.engineers})
    engineers = instance.engineers
    requests = [instance.requests[request_index] for request_index in task_request_indices]
    objective = build_objective_policy(
        instance,
        task_request_indices,
        settings.cuopt_distance_weight if distance_weight is None else distance_weight,
    )

    return SolverInputs(
        location_count=instance.n_engineers + instance.n_requests,
        cost_matrices={
            transport_id: (instance.distance_km[transport_id] / objective.distance_scale).astype(
                np.float32
            )
            for transport_id in transport_ids
        },
        travel_time_matrices={
            transport_id: instance.travel_min[transport_id].astype(np.float32) for transport_id in transport_ids
        },
        vehicle_locations=np.array(
            [instance.start_node(engineer_index) for engineer_index in range(instance.n_engineers)], dtype=np.int32
        ),
        vehicle_types=np.array([engineer.transport_id for engineer in engineers], dtype=np.uint8),
        vehicle_shift_start=np.array([engineer.shift_start_min for engineer in engineers], dtype=np.int32),
        vehicle_shift_end=np.array([engineer.shift_end_min for engineer in engineers], dtype=np.int32),
        vehicle_fixed_costs=np.full(
            instance.n_engineers, objective.vehicle_cost, dtype=np.float32
        ),
        order_locations=np.array(
            [instance.request_node(request_index) for request_index in task_request_indices], dtype=np.int32
        ),
        order_window_start=np.array([request.window_start_min for request in requests], dtype=np.int32),
        order_window_end=np.array([request.window_end_min for request in requests], dtype=np.int32),
        order_service_minutes=np.array([request.duration_min for request in requests], dtype=np.int32),
        order_prizes=np.array(
            [
                objective.urgent_reward if request.is_urgent else objective.regular_reward
                for request in requests
            ],
            dtype=np.float32,
        ),
        order_allowed_vehicles=[
            np.array(instance.candidates(request_index), dtype=np.int32) for request_index in task_request_indices
        ],
        objective=objective,
    )


def build_objective_policy(
    instance: ProblemInstance,
    task_request_indices: list[int],
    distance_weight: float,
) -> ObjectivePolicy:
    """Строит безопасные Big-M коэффициенты для приоритетов ТЗ.

    Cost-матрицы делятся на верхнюю границу суммарного пробега. Поэтому вклад COST
    любого решения не больше distance_weight и остальные уровни можно отделить
    небольшими динамическими коэффициентами, не зависящими от единиц расстояния.
    """
    if not math.isfinite(distance_weight) or distance_weight < 0:
        raise ValueError("вес пробега cuOpt должен быть конечным неотрицательным числом")

    request_count = len(task_request_indices)
    regular_count = sum(
        not instance.requests[index].is_urgent for index in task_request_indices
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
    feasible_arc_distances = []
    for transport_id, distance_matrix in instance.distance_km.items():
        travel_matrix = instance.travel_min[transport_id]
        feasible = (
            np.isfinite(travel_matrix)
            & (travel_matrix >= 0)
            & (travel_matrix <= max_shift_span)
        )
        if feasible.any():
            feasible_arc_distances.append(float(np.max(distance_matrix[feasible])))
    max_arc_distance = max(feasible_arc_distances, default=0.0)

    # Без возврата в депо у каждой выполненной заявки ровно одно входящее плечо.
    distance_scale = max(request_count * max_arc_distance, 1.0)
    lower_distance_cost = distance_weight
    vehicle_cost = lower_distance_cost + 1.0
    lower_regular_cost = instance.n_engineers * vehicle_cost + lower_distance_cost
    regular_reward = lower_regular_cost + 1.0
    lower_urgent_cost = regular_count * regular_reward + lower_regular_cost
    urgent_reward = lower_urgent_cost + 1.0

    maximum_objective_magnitude = (
        request_count * urgent_reward + lower_regular_cost
    )
    values = (
        distance_scale,
        vehicle_cost,
        regular_reward,
        urgent_reward,
        maximum_objective_magnitude,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("коэффициенты целевой функции cuOpt вышли за допустимый диапазон")
    if maximum_objective_magnitude > FLOAT32_SAFE_OBJECTIVE:
        raise ValueError(
            "задача слишком велика для безопасной одноэтапной float32 objective cuOpt; "
            "нужен многоэтапный расчёт"
        )

    return ObjectivePolicy(
        urgent_reward=urgent_reward,
        regular_reward=regular_reward,
        vehicle_cost=vehicle_cost,
        distance_weight=distance_weight,
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
    assignment = routing.Solve(data_model, solver_settings)

    if assignment.get_status() != SOLVE_SUCCESS:
        raise ExternalServiceError(f"cuOpt не нашёл решение: статус {assignment.get_status()}")
    return assignment.get_route().to_pandas().to_dict("records")


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
            raise ExternalServiceError("cuOpt вернул неизвестного исполнителя")
        engineer = instance.engineers[engineer_index]
        previous_node = instance.start_node(engineer_index)
        available: float = engineer.shift_start_min
        for visit in visits:
            index = visit.request_index
            if not 0 <= index < instance.n_requests or index in seen:
                raise ExternalServiceError("cuOpt вернул неизвестную или повторную заявку")
            seen.add(index)
            request = instance.requests[index]
            start = visit.work_start_minute
            arrival = available + instance.travel_min[engineer.transport_id][previous_node, instance.request_node(index)]
            if (not math.isfinite(start) or not instance.compatible[index, engineer_index]
                    or start < max(arrival, request.window_start_min) - 1e-4
                    or start > request.window_end_min + 1e-4
                    or start + request.duration_min > engineer.shift_end_min + 1e-4):
                raise ExternalServiceError("Результат cuOpt нарушает ограничения заявки или смены")
            available = start + request.duration_min
            previous_node = instance.request_node(index)
