"""Раздел 4.3: связность маршрута и открытый маршрут (ТЗ 2.4 — без возврата в старт).

Правка к исходной постановке. Там записано

    sum_v x^k_iv = y^k_i   и   sum_v x^k_vi = y^k_i,

но при открытом маршруте у последней заявки исходящей дуги нет, и первое равенство
делает модель неразрешимой при любом непустом маршруте. Вводим фиктивный узел-финиш:
дуги (заявка -> финиш) стоят 0 км и 0 минут, поэтому на метрики не влияют, а поток
сходится:

    sum_{u} x^k_ui        = y^k_i           входящий поток в заявку
    sum_{v} x^k_iv        = y^k_i           исходящий (v включает финиш)
    sum_{v} x^k_{s_k, v}  = u_k             выезд со старта — только если инженер занят
    sum_{i} x^k_{i, финиш} = u_k            ровно один обрыв маршрута
    sum_{v} x^k_{v, s_k}  = 0               в старт не возвращаемся (таких дуг просто нет)

Отдельных ограничений на подциклы не требуется: их отсекают временные ограничения
(раздел 4.4), поскольку tau строго растёт вдоль дуги, а в цикле это невозможно.
"""

from src.services.planner.constraints.constraint_block import ConstraintBlock
from src.services.planner.planner_variables import VariableLayout


def build(layout: VariableLayout) -> ConstraintBlock:
    instance = layout.instance
    block = ConstraintBlock(label="flow", sense="eq", n_variables=layout.n_variables)

    for k in range(instance.n_engineers):
        engineer_id = instance.engineers[k].engineer_id

        for i in range(instance.n_requests):
            if not instance.compatible[i, k]:
                continue
            node = instance.request_node(i)
            assign_column = layout.assign_column(k, i)
            request_id = instance.requests[i].request_id

            incoming = {int(layout.arc_column(a)): 1.0 for a in layout.arcs_into(node, k)}
            incoming[assign_column] = incoming.get(assign_column, 0.0) - 1.0
            block.add_row(incoming, rhs=0.0, label=f"in:e={engineer_id},r={request_id}")

            outgoing = {int(layout.arc_column(a)): 1.0 for a in layout.arcs_out_of(node, k)}
            outgoing[assign_column] = outgoing.get(assign_column, 0.0) - 1.0
            block.add_row(outgoing, rhs=0.0, label=f"out:e={engineer_id},r={request_id}")

        usage_column = layout.usage_column(k)

        departures = {
            int(layout.arc_column(a)): 1.0
            for a in layout.arcs_out_of(instance.start_node(k), k)
        }
        departures[usage_column] = departures.get(usage_column, 0.0) - 1.0
        block.add_row(departures, rhs=0.0, label=f"depart:e={engineer_id}")

        terminations = {
            int(layout.arc_column(a)): 1.0
            for a in layout.arcs_into(instance.end_node, k)
        }
        terminations[usage_column] = terminations.get(usage_column, 0.0) - 1.0
        block.add_row(terminations, rhs=0.0, label=f"finish:e={engineer_id}")

    return block
