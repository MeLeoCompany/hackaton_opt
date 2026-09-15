"""Раздел 4.4: согласование времён вдоль маршрута (ограничение «Время» из ТЗ 2.2).

Три группы неравенств (окно самой заявки a_i <= tau_i <= b_i задаётся не строкой
матрицы, а границами переменной — см. planner_milp):

1. Между заявками, если инженер k едет из i в j:
       tau_j >= tau_i + p_i + t^k_ij
   в линейном виде с большим M:
       tau_i - tau_j + M * x^k_ij <= M - p_i - t^k_ij

2. От стартовой точки инженера к первой заявке:
       tau_j >= alpha_k + t^k_{s_k,j}
       -tau_j + M * x^k_{s_k,j} <= M - alpha_k - t^k_{s_k,j}

3. Работы заканчиваются до конца смены, если заявка назначена этому инженеру:
       tau_i + p_i <= beta_k
       tau_i + M * y^k_i <= beta_k - p_i + M

M берётся отдельным для каждой строки и настолько малым, насколько это корректно:
слабый (одинаковый большой) M разваливает непрерывную релаксацию и резко замедляет
любой MILP-решатель. Например, для (1) максимально возможное нарушение равно
b_i + p_i + t_ij - a_j, больший M смысла не имеет.

Раннее прибытие разрешено: инженер ждёт открытия окна, штрафа за ожидание нет
(неравенство, а не равенство).

Побочный эффект этой группы — отсечение подциклов: вдоль дуги tau строго растёт
(p_i + t_ij > 0), поэтому замкнутый цикл среди заявок невозможен.
"""

from src.services.planner.constraints.constraint_block import ConstraintBlock
from src.services.planner.planner_variables import VariableLayout


def build(layout: VariableLayout) -> ConstraintBlock:
    instance = layout.instance
    block = ConstraintBlock(label="time", sense="ub", n_variables=layout.n_variables)

    _add_arc_precedence(layout, block)
    _add_shift_end(layout, block)
    return block


def _add_arc_precedence(layout: VariableLayout, block: ConstraintBlock) -> None:
    instance = layout.instance

    for arc in range(layout.n_arcs):
        k = int(layout.arc_engineer[arc])
        source = int(layout.arc_from[arc])
        target = int(layout.arc_to[arc])

        if target == instance.end_node:
            continue  # фиктивный финиш во времени не участвует

        target_index = target - instance.n_engineers
        target_request = instance.requests[target_index]
        travel = instance.travel_for(k, source, target)
        arc_column = layout.arc_column(arc)

        if source < instance.n_engineers:
            # выезд со старта смены
            departure = instance.engineers[k].shift_start_min
            big_m = max(0.0, departure + travel - target_request.window_start_min)
            if big_m == 0.0:
                continue  # даже выехав в начале смены, инженер не опередит окно
            block.add_row(
                {
                    layout.start_time_column(target_index): -1.0,
                    arc_column: big_m,
                },
                rhs=big_m - departure - travel,
                label=f"start:e={instance.engineers[k].engineer_id},r={target_request.request_id}",
            )
            continue

        source_index = source - instance.n_engineers
        source_request = instance.requests[source_index]
        offset = source_request.duration_min + travel
        big_m = max(
            0.0,
            source_request.window_end_min + offset - target_request.window_start_min,
        )
        if big_m == 0.0:
            continue
        block.add_row(
            {
                layout.start_time_column(source_index): 1.0,
                layout.start_time_column(target_index): -1.0,
                arc_column: big_m,
            },
            rhs=big_m - offset,
            label=f"seq:e={instance.engineers[k].engineer_id},"
            f"{source_request.request_id}->{target_request.request_id}",
        )


def _add_shift_end(layout: VariableLayout, block: ConstraintBlock) -> None:
    instance = layout.instance

    for (k, i), _ in layout.assign_index.items():
        request = instance.requests[i]
        engineer = instance.engineers[k]
        latest_start = engineer.shift_end_min - request.duration_min
        big_m = max(0.0, request.window_end_min - latest_start)
        if big_m == 0.0:
            continue  # окно и так закрывается раньше, чем смена
        block.add_row(
            {
                layout.start_time_column(i): 1.0,
                layout.assign_column(k, i): big_m,
            },
            rhs=latest_start + big_m,
            label=f"shift:e={engineer.engineer_id},r={request.request_id}",
        )
