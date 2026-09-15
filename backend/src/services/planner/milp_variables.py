"""Шаг 1. Переменные задачи и их границы."""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_variables(problem: MilpProblem, instance: ProblemInstance) -> None:
    add_drive_variables(problem, instance)

    # «заявка назначена инженеру» — только для пар, где у инженера есть навык и транспорт
    for engineer_index in range(instance.n_engineers):
        for request_index in range(instance.n_requests):
            if instance.compatible[request_index, engineer_index]:
                problem.assigned_column[(engineer_index, request_index)] = problem.add_variable(
                    0.0, 1.0, is_integer=True
                )

    # «у инженера есть хотя бы одна заявка»
    for engineer_index in range(instance.n_engineers):
        problem.engineer_used_column[engineer_index] = problem.add_variable(0.0, 1.0, is_integer=True)

    # «заявка никому не назначена»
    for request_index in range(instance.n_requests):
        problem.unassigned_column[request_index] = problem.add_variable(0.0, 1.0, is_integer=True)

    # «время начала работ» — сразу ограничено окном заявки
    for request_index, request in enumerate(instance.requests):
        problem.work_start_column[request_index] = problem.add_variable(
            request.window_start_min, request.window_end_min, is_integer=False
        )


def add_drive_variables(problem: MilpProblem, instance: ProblemInstance) -> None:
    """Переменные «инженер едет из одной точки прямо в другую».

    У каждого инженера маршрут выглядит так:  старт -> заявка -> заявка -> ... -> финиш.
    Заводим переменную только для тех переездов, которые реально можно совершить
    по времени. Остальные решатель всё равно никогда бы не выбрал.
    """
    for engineer_index in range(instance.n_engineers):
        # заявки, которые этому инженеру вообще можно отдать (навык и транспорт)
        engineer_requests = [
            request_index
            for request_index in range(instance.n_requests)
            if instance.compatible[request_index, engineer_index]
        ]
        start_node = instance.start_node(engineer_index)

        # 1) со старта на первую заявку
        for request_index in engineer_requests:
            if can_start_route_with(instance, engineer_index, request_index):
                problem.add_drive(engineer_index, start_node, instance.request_node(request_index))

        # 2) с одной заявки на другую
        for from_request_index in engineer_requests:
            for to_request_index in engineer_requests:
                if from_request_index == to_request_index:
                    continue
                if can_drive_between(instance, engineer_index, from_request_index, to_request_index):
                    problem.add_drive(
                        engineer_index,
                        instance.request_node(from_request_index),
                        instance.request_node(to_request_index),
                    )

        # 3) с последней заявки на финиш (возврата на старт нет, финиш фиктивный)
        for request_index in engineer_requests:
            problem.add_drive(engineer_index, instance.request_node(request_index), instance.end_node)


def can_start_route_with(instance: ProblemInstance, engineer_index: int, request_index: int) -> bool:
    """Может ли инженер поехать на эту заявку первой, прямо со своей стартовой точки.

    Выезжает в начало смены -> едет -> если приехал раньше окна, ждёт.
    Подходит, если успевает начать до закрытия окна и закончить до конца смены.
    """
    engineer = instance.engineers[engineer_index]
    request = instance.requests[request_index]
    drive_minutes = instance.travel_for(
        engineer_index, instance.start_node(engineer_index), instance.request_node(request_index)
    )

    arrival = engineer.shift_start_min + drive_minutes
    work_start = max(arrival, request.window_start_min)
    work_end = work_start + request.duration_min

    return work_start <= request.window_end_min and work_end <= engineer.shift_end_min


def can_drive_between(
    instance: ProblemInstance, engineer_index: int, from_request_index: int, to_request_index: int
) -> bool:
    """Может ли инженер после одной заявки сразу поехать на другую.

    Берём самый удачный случай: первую заявку начали ровно в момент открытия её окна.
    Если даже тогда не успеть к закрытию окна второй — такой переезд невозможен никогда.

    Пример: первая в окне 15:00-17:00, вторая в окне 10:00-12:00, работа 60 мин, дорога 10 мин.
    Самое раннее прибытие на вторую: 15:00 + 60 + 10 = 16:10 — её окно закрылось в 12:00. Нельзя.
    """
    first_request = instance.requests[from_request_index]
    second_request = instance.requests[to_request_index]
    drive_minutes = instance.travel_for(
        engineer_index,
        instance.request_node(from_request_index),
        instance.request_node(to_request_index),
    )

    earliest_arrival = first_request.window_start_min + first_request.duration_min + drive_minutes
    return earliest_arrival <= second_request.window_end_min
