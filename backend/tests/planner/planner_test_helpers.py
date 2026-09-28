"""Вспомогательные функции для тестов планировщика.

Задачи собираются вручную с простыми матрицами — одинаковое время и расстояние между любыми
двумя разными точками, — чтобы правильный ответ можно было посчитать в уме.

constraint_violations — независимая проверка результата решателя по ограничениям ТЗ (п. 2.2):
она не использует код планировщика, а заново сверяет каждый визит с исходными данными.
"""

import asyncio

import numpy as np

from src.schemas.system import SolverParams
from src.services.planner import EngineerSpec, ProblemInstance, RequestSpec, build_compatibility
from src.services.planner.cuopt_solver import DaySolution, solve_day
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER, ObjectiveCriterion

CAR = 1
WALK = 2
BIKE = 3

# уровни приоритета из справочника (db/init/032): авария важнее подключения, подключение —
# важнее ремонта и дозаказа
EMERGENCY = 1
CONNECTION = 2
REGULAR = 3
URGENT = EMERGENCY

# arrival_stamp у cuOpt дробный — сравниваем с небольшим допуском
MINUTE_TOLERANCE = 1e-6


def hhmm(clock_time: str) -> int:
    """'10:00' -> 600 минут от начала дня."""
    hours, minutes = clock_time.split(":")
    return int(hours) * 60 + int(minutes)


def as_clock(minutes: float) -> str:
    """600.0 -> '10:00' — для понятных сообщений в тестах."""
    whole_minutes = round(minutes)
    return f"{whole_minutes // 60:02d}:{whole_minutes % 60:02d}"


def engineer(engineer_id, transport=CAR, shift=("08:00", "18:00"), equipment=None):
    return EngineerSpec(
        engineer_id,
        f"исполнитель {engineer_id}",
        transport,
        hhmm(shift[0]),
        hhmm(shift[1]),
        equipment_capacity=equipment or {},
    )


def request(
    request_id,
    skill,
    window,
    duration=60,
    transport=None,
    priority=REGULAR,
    equipment=None,
):
    return RequestSpec(
        request_id,
        duration,
        hhmm(window[0]),
        hhmm(window[1]),
        skill,
        transport,
        priority,
        equipment_demand=equipment or {},
    )


def make_instance(
    engineers, requests, skills, travel_min=10, distance_km=5.0, travel_min_by_transport=None
):
    """Задача, где между любыми двумя разными точками travel_min минут и distance_km км.

    skills — навыки по engineer_id, например {1: {1, 2}, 2: {3}}.
    travel_min_by_transport — своё время в пути для отдельных транспортов, например {WALK: 90}.
    """
    point_count = len(engineers) + len(requests)
    transports = {each.transport_id for each in engineers}
    travel_overrides = travel_min_by_transport or {}

    def same_everywhere(value, dtype):
        matrix = np.full((point_count, point_count), value, dtype=dtype)
        np.fill_diagonal(matrix, 0)
        return matrix

    instance = ProblemInstance(
        engineers=engineers,
        requests=requests,
        distance_km={
            transport: same_everywhere(distance_km, np.float64) for transport in transports
        },
        travel_min={
            transport: same_everywhere(travel_overrides.get(transport, travel_min), np.int32)
            for transport in transports
        },
    )
    build_compatibility(instance, skills)
    return instance


# задачи в тестах крошечные: двух секунд поиска решателю хватает с запасом
TEST_SOLVER_PARAMS = SolverParams(time_limit_seconds=2.0)


def solve(
    instance: ProblemInstance,
    objective_order: tuple[ObjectiveCriterion, ...] = DEFAULT_OBJECTIVE_ORDER,
) -> DaySolution:
    return asyncio.run(
        solve_day(instance, objective_order=objective_order, params=TEST_SOLVER_PARAMS)
    )


def assigned_request_ids(instance: ProblemInstance, solution: DaySolution) -> list[int]:
    return sorted(
        instance.requests[visit.request_index].request_id
        for visits in solution.routes.values()
        for visit in visits
    )


def route_request_ids(
    instance: ProblemInstance, solution: DaySolution, engineer_id: int
) -> list[int]:
    """Номера заявок исполнителя в порядке объезда."""
    for engineer_index, visits in solution.routes.items():
        if instance.engineers[engineer_index].engineer_id == engineer_id:
            return [instance.requests[visit.request_index].request_id for visit in visits]
    return []


def constraint_violations(
    instance: ProblemInstance, skills: dict[int, set[int]], solution: DaySolution
) -> list[str]:
    """Все нарушения ограничений ТЗ в решении; пустой список — решение допустимо.

    Проверяется по исходным данным, а не по подготовленной планировщиком совместимости:
      - каждая заявка назначена не больше одного раза;
      - квалификация: навык заявки есть у исполнителя;
      - ресурс: требуемый транспорт совпадает с транспортом исполнителя;
      - время: начало работ не раньше, чем исполнитель доедет (от старта смены или от конца
        предыдущей работы), попадает в окно заявки, работа заканчивается до конца смены.
    """
    violations = []
    assigned_to = {}

    for engineer_index, visits in solution.routes.items():
        engineer_spec = instance.engineers[engineer_index]
        travel = instance.travel_min[engineer_spec.transport_id]
        position = instance.start_node(engineer_index)
        free_from = engineer_spec.shift_start_min
        equipment_used = {}

        for visit in visits:
            request_spec = instance.requests[visit.request_index]
            label = f"заявка {request_spec.request_id} у исполнителя {engineer_spec.engineer_id}"

            if visit.request_index in assigned_to:
                violations.append(
                    f"{label}: уже назначена исполнителю {assigned_to[visit.request_index]}"
                )
            assigned_to[visit.request_index] = engineer_spec.engineer_id

            if request_spec.skill_id not in skills[engineer_spec.engineer_id]:
                violations.append(f"{label}: нет навыка {request_spec.skill_id}")
            if (
                request_spec.required_transport_id is not None
                and request_spec.required_transport_id != engineer_spec.transport_id
            ):
                violations.append(f"{label}: нужен транспорт {request_spec.required_transport_id}")
            for equipment_id, quantity in request_spec.equipment_demand.items():
                equipment_used[equipment_id] = equipment_used.get(equipment_id, 0) + quantity
                if equipment_used[equipment_id] > engineer_spec.equipment_capacity.get(
                    equipment_id, 0
                ):
                    violations.append(f"{label}: не хватает оборудования {equipment_id}")

            earliest_start = (
                free_from + travel[position][instance.request_node(visit.request_index)]
            )
            work_start = visit.work_start_minute
            if work_start + MINUTE_TOLERANCE < earliest_start:
                violations.append(
                    f"{label}: начало {as_clock(work_start)} раньше, чем можно доехать ({as_clock(earliest_start)})"
                )
            if not (
                request_spec.window_start_min - MINUTE_TOLERANCE
                <= work_start
                <= request_spec.window_end_min + MINUTE_TOLERANCE
            ):
                violations.append(
                    f"{label}: начало {as_clock(work_start)} вне окна "
                    f"{as_clock(request_spec.window_start_min)}-{as_clock(request_spec.window_end_min)}"
                )

            work_end = work_start + request_spec.duration_min
            if work_end > engineer_spec.shift_end_min + MINUTE_TOLERANCE:
                violations.append(
                    f"{label}: работа кончается в {as_clock(work_end)}, "
                    f"после конца смены {as_clock(engineer_spec.shift_end_min)}"
                )

            free_from = work_end
            position = instance.request_node(visit.request_index)

    return violations
