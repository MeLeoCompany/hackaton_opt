"""Раздел 4.2: каждая заявка либо назначена ровно одному инженеру, либо не назначена.

    sum_{k in E_i} y^k_i + z_i = 1   для каждой заявки i
"""

from src.services.planner.constraints.constraint_block import ConstraintBlock
from src.services.planner.planner_variables import VariableLayout


def build(layout: VariableLayout) -> ConstraintBlock:
    instance = layout.instance
    block = ConstraintBlock(
        label="assignment", sense="eq", n_variables=layout.n_variables
    )

    for i in range(instance.n_requests):
        terms = {
            layout.assign_column(k, i): 1.0
            for k in instance.candidates(i)
        }
        terms[layout.unassigned_column(i)] = 1.0
        block.add_row(terms, rhs=1.0, label=f"request={instance.requests[i].request_id}")

    return block
