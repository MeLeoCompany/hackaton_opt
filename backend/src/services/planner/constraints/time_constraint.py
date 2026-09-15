"""4.4 Время: инженер успевает доехать, отработать и закончить до конца смены.

Три правила:
    1. Первая заявка начинается не раньше, чем инженер доедет до неё от старта.
    2. Следующая заявка начинается не раньше, чем закончится предыдущая плюс дорога.
    3. Работа по заявке заканчивается до конца смены того, кому она назначена.

То, что работа начинается внутри окна заявки, уже задано границами переменной
«время начала работ» в milp_variables — отдельные строки для этого не нужны.

Как «выключается» правило, если инженер по этому переезду не едет.
Правило должно действовать, только когда переменная переезда равна 1. Для этого в строку
добавляется запас big_m, умноженный на эту переменную:
    - переезд выбран (1):  запас сокращается, остаётся исходное правило;
    - переезд не выбран (0): к правой части добавлен запас, и неравенство выполняется
      при любых допустимых временах, то есть ничего не ограничивает.
Запас берём минимально достаточным — ровно на сколько правило могло бы быть нарушено.
Если нарушить его невозможно (запас получился 0), строку вообще не добавляем.
"""

from src.services.planner.milp_problem import MilpProblem
from src.services.planner.planner_problem import ProblemInstance


def add_time_constraint(problem: MilpProblem, instance: ProblemInstance) -> None:
    for (engineer_index, from_node, to_node), drive_column in problem.drive_column.items():
        if to_node == instance.end_node:
            continue  # на финиш время не проверяем — он фиктивный

        if from_node == instance.start_node(engineer_index):
            add_drive_from_start_row(problem, instance, engineer_index, to_node, drive_column)
        else:
            add_drive_between_requests_row(
                problem, instance, engineer_index, from_node, to_node, drive_column
            )

    add_finish_before_shift_end_rows(problem, instance)


def add_drive_from_start_row(
    problem: MilpProblem,
    instance: ProblemInstance,
    engineer_index: int,
    request_node: int,
    drive_column: int,
) -> None:
    """Правило 1. Если инженер едет со старта на заявку:

        начало работ >= начало смены + дорога

    В виде строки:  -начало_работ + big_m · переезд <= big_m - начало_смены - дорога
    """
    request_index = request_node - instance.n_engineers
    request = instance.requests[request_index]
    shift_start = instance.engineers[engineer_index].shift_start_min
    drive_minutes = instance.travel_for(engineer_index, instance.start_node(engineer_index), request_node)

    # насколько правило может быть нарушено: самое раннее начало работ — открытие окна
    big_m = max(0.0, shift_start + drive_minutes - request.window_start_min)
    if big_m == 0:
        return  # доехать можно ещё до открытия окна — правило ничего не ограничивает

    work_start_column = problem.work_start_column[request_index]
    problem.add_row(
        [(work_start_column, -1.0), (drive_column, big_m)],
        "<=",
        big_m - shift_start - drive_minutes,
    )


def add_drive_between_requests_row(
    problem: MilpProblem,
    instance: ProblemInstance,
    engineer_index: int,
    from_node: int,
    to_node: int,
    drive_column: int,
) -> None:
    """Правило 2. Если инженер едет с одной заявки на другую:

        начало работ второй >= начало работ первой + длительность первой + дорога

    В виде строки:
        начало_первой - начало_второй + big_m · переезд <= big_m - (длительность + дорога)
    """
    first_index = from_node - instance.n_engineers
    second_index = to_node - instance.n_engineers
    first_request = instance.requests[first_index]
    second_request = instance.requests[second_index]

    drive_minutes = instance.travel_for(engineer_index, from_node, to_node)
    work_and_drive_minutes = first_request.duration_min + drive_minutes

    # насколько правило может быть нарушено: первую начали в самый поздний момент,
    # вторую — в самый ранний
    big_m = max(
        0.0,
        first_request.window_end_min + work_and_drive_minutes - second_request.window_start_min,
    )
    if big_m == 0:
        return  # даже в худшем случае вторая успевает — правило ничего не ограничивает

    problem.add_row(
        [
            (problem.work_start_column[first_index], 1.0),
            (problem.work_start_column[second_index], -1.0),
            (drive_column, big_m),
        ],
        "<=",
        big_m - work_and_drive_minutes,
    )


def add_finish_before_shift_end_rows(problem: MilpProblem, instance: ProblemInstance) -> None:
    """Правило 3. Если заявка назначена инженеру:

        начало работ + длительность <= конец смены

    В виде строки:  начало_работ + big_m · назначена <= конец_смены - длительность + big_m
    """
    for (engineer_index, request_index), assigned_column in problem.assigned_column.items():
        request = instance.requests[request_index]
        shift_end = instance.engineers[engineer_index].shift_end_min
        latest_work_start = shift_end - request.duration_min

        # насколько правило может быть нарушено: работу начали в самый поздний момент окна
        big_m = max(0.0, request.window_end_min - latest_work_start)
        if big_m == 0:
            continue  # окно закрывается раньше, чем кончается смена, — правило лишнее

        problem.add_row(
            [(problem.work_start_column[request_index], 1.0), (assigned_column, big_m)],
            "<=",
            latest_work_start + big_m,
        )
