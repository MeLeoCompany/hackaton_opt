"""Раздел 4.5: инженер считается задействованным, если у него есть хотя бы одна заявка.

    y^k_i - u_k <= 0

Связывает назначения с переменной u_k, по которой в целевой функции берётся плата
за задействование инженера (метрика ТЗ 2.3 «минимум персонала»).
"""

from src.services.planner.constraints.constraint_block import ConstraintBlock
from src.services.planner.planner_variables import VariableLayout


def build(layout: VariableLayout) -> ConstraintBlock:
    instance = layout.instance
    block = ConstraintBlock(label="usage", sense="ub", n_variables=layout.n_variables)

    for k, i in layout.assign_index:
        block.add_row(
            {
                layout.assign_column(k, i): 1.0,
                layout.usage_column(k): -1.0,
            },
            rhs=0.0,
            label=f"usage:e={instance.engineers[k].engineer_id},r={instance.requests[i].request_id}",
        )

    return block
