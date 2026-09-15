"""Решение задачи дня в cuOpt через Python SDK: ProblemInstance -> routing.DataModel -> маршруты.

Как наша задача ложится на модель cuOpt:
  исполнитель          -> vehicle: старт в его точке, возврата нет, окно = смена, тип = транспорт
  заявка               -> order: окно, длительность работы, приз по приоритету
  навык и транспорт    -> order_vehicle_match: кому из исполнителей заявку вообще можно отдать
  километры            -> cost-матрица: по ней минимизируется пробег
  минуты в пути        -> матрица времени в пути: по ней проверяется, что всё успеваем
  неназначенная заявка -> недополученный приз (срочная стоит дороже)

Заявки, которые не подходят ни одному исполнителю, в cuOpt не отправляются.

Решатель считает на видеокарте NVIDIA прямо в процессе бэкенда. Пакет cuopt-cu12 ставится
с https://pypi.nvidia.com и импортируется только при решении, поэтому остальной бэкенд
и тесты сборки задачи работают и без него.
"""

import asyncio
from dataclasses import dataclass, field

import numpy as np

from src.core.config import settings
from src.core.errors import ExternalServiceError
from src.services.planner.planner_problem import ProblemInstance

# цены в тех же единицах, что cost-матрица, то есть в километрах:
# выгоднее проехать лишнюю сотню километров, чем бросить заявку
PRIZE_PER_REQUEST = 1000.0
# цена задействования ещё одного исполнителя
ENGINEER_FIXED_COST = 50.0

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


@dataclass
class SolverInputs:
    """Всё, что загружается в DataModel, — массивами numpy в тех типах, которые ждёт cuOpt.

    Номер исполнителя здесь = номер vehicle в cuOpt, номер заявки в списке = номер order.
    """

    location_count: int
    cost_matrices: dict[int, np.ndarray]  # тип транспорта -> км между точками, float32
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


async def solve_day(instance: ProblemInstance) -> DaySolution:
    task_request_indices = schedulable_request_indices(instance)
    if not task_request_indices or instance.n_engineers == 0:
        return DaySolution()

    inputs = build_solver_inputs(instance, task_request_indices)
    # решение занимает секунды — считаем в отдельном потоке, чтобы не блокировать остальные запросы
    route_records = await asyncio.to_thread(run_cuopt, inputs, settings.cuopt_time_limit_seconds)
    return parse_route_records(route_records, task_request_indices)


def schedulable_request_indices(instance: ProblemInstance) -> list[int]:
    """Заявки, которые подходят хотя бы одному исполнителю, — только их отправляем в cuOpt."""
    return [
        request_index
        for request_index in range(instance.n_requests)
        if instance.compatible[request_index].any()
    ]


def build_solver_inputs(instance: ProblemInstance, task_request_indices: list[int]) -> SolverInputs:
    """ProblemInstance -> массивы для DataModel. task_request_indices — какие заявки отправляем."""
    transport_ids = sorted({engineer.transport_id for engineer in instance.engineers})
    engineers = instance.engineers
    requests = [instance.requests[request_index] for request_index in task_request_indices]

    return SolverInputs(
        location_count=instance.n_engineers + instance.n_requests,
        cost_matrices={
            transport_id: instance.distance_km[transport_id].astype(np.float32) for transport_id in transport_ids
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
        vehicle_fixed_costs=np.full(instance.n_engineers, ENGINEER_FIXED_COST, dtype=np.float32),
        order_locations=np.array(
            [instance.request_node(request_index) for request_index in task_request_indices], dtype=np.int32
        ),
        order_window_start=np.array([request.window_start_min for request in requests], dtype=np.int32),
        order_window_end=np.array([request.window_end_min for request in requests], dtype=np.int32),
        order_service_minutes=np.array([request.duration_min for request in requests], dtype=np.int32),
        order_prizes=np.array([PRIZE_PER_REQUEST * request.priority_weight for request in requests], dtype=np.float32),
        order_allowed_vehicles=[
            np.array(instance.candidates(request_index), dtype=np.int32) for request_index in task_request_indices
        ],
    )


def run_cuopt(inputs: SolverInputs, time_limit_seconds: float) -> list[dict]:
    """Загружает задачу в DataModel, решает и возвращает таблицу маршрутов строками."""
    try:
        from cuopt import routing
    except ImportError as error:
        raise ExternalServiceError(
            "Решатель cuOpt не установлен: pip install cuopt-cu12 --extra-index-url https://pypi.nvidia.com"
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

    solver_settings = routing.SolverSettings()
    solver_settings.set_time_limit(time_limit_seconds)
    assignment = routing.Solve(data_model, solver_settings)

    if assignment.get_status() != SOLVE_SUCCESS:
        raise ExternalServiceError(f"cuOpt не нашёл решение: статус {assignment.get_status()}")
    return assignment.get_route().to_pandas().to_dict("records")


def parse_route_records(route_records: list[dict], task_request_indices: list[int]) -> DaySolution:
    """Таблица маршрутов cuOpt -> визиты по исполнителям в порядке объезда.

    Каждая строка — одна остановка: vehicle_id (номер исполнителя), route (номер заявки
    в списке отправленных), arrival_stamp (время начала работ в минутах от начала дня),
    type (Depot — старт, Delivery — заявка). Строки одного исполнителя идут по порядку объезда.
    """
    solution = DaySolution()
    for record in route_records:
        if record["type"] != "Delivery":
            continue
        engineer_index = int(record["vehicle_id"])
        visit = PlannedVisit(
            request_index=task_request_indices[int(record["route"])],
            work_start_minute=float(record["arrival_stamp"]),
        )
        solution.routes.setdefault(engineer_index, []).append(visit)
    return solution
