"""Сборка задачи в матричный вид, не привязанный к решателю.

На выходе — каноническая форма смешанно-целочисленной задачи:

    min c^T x
    при  A_eq  x  = b_eq
         A_ub  x <= b_ub
         lower <= x <= upper
         integrality: 1 — целочисленная (все булевы), 0 — непрерывная (tau)

В таком виде задачу принимают scipy.optimize.milp/HiGHS, CBC, Gurobi и любой другой
MILP-решатель. Специализированные решатели маршрутизации (cuOpt, OR-Tools) матрицы не
используют — они читают ProblemInstance напрямую, поэтому матричная сборка им не мешает.
"""

import time
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

from src.services.planner.constraints import (
    assignment_constraint,
    flow_constraint,
    time_constraint,
    usage_constraint,
)
from src.services.planner.constraints.constraint_block import ConstraintBlock
from src.services.planner.planner_objective import ObjectiveWeights, build as build_objective
from src.services.planner.planner_problem import ProblemInstance
from src.services.planner.planner_variables import VariableLayout


@dataclass
class MilpProblem:
    layout: VariableLayout
    costs: np.ndarray
    a_eq: sp.csr_matrix
    b_eq: np.ndarray
    a_ub: sp.csr_matrix
    b_ub: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    integrality: np.ndarray
    blocks: list[ConstraintBlock] = field(default_factory=list)
    build_seconds: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        layout = self.layout
        rows = [
            f"переменных: {layout.n_variables}"
            f"  (дуги {layout.n_arcs}, назначения {layout.n_assignments},"
            f" занятость {layout.instance.n_engineers},"
            f" неназначенные {layout.instance.n_requests},"
            f" времёна {layout.instance.n_requests})",
            f"ограничений: равенств {self.a_eq.shape[0]}, неравенств {self.a_ub.shape[0]}",
            f"ненулевых в матрицах: {self.a_eq.nnz + self.a_ub.nnz}",
            f"плотность: {self._density():.2e}",
        ]
        for block in self.blocks:
            rows.append(
                f"  блок {block.label:<11} {block.sense:>2}  строк {block.n_rows:>6}"
                f"  ненулевых {block.n_nonzeros:>7}"
                f"  {self.build_seconds.get(block.label, 0.0) * 1000:7.1f} мс"
            )
        return "\n".join(rows)

    def _density(self) -> float:
        cells = (self.a_eq.shape[0] + self.a_ub.shape[0]) * self.layout.n_variables
        return (self.a_eq.nnz + self.a_ub.nnz) / cells if cells else 0.0


def build(
    instance: ProblemInstance, weights: ObjectiveWeights | None = None
) -> MilpProblem:
    weights = weights or ObjectiveWeights()
    timings: dict[str, float] = {}

    started = time.perf_counter()
    layout = VariableLayout(instance)
    timings["layout"] = time.perf_counter() - started

    blocks: list[ConstraintBlock] = []
    for module in (assignment_constraint, flow_constraint, time_constraint, usage_constraint):
        started = time.perf_counter()
        block = module.build(layout)
        timings[block.label] = time.perf_counter() - started
        blocks.append(block)

    started = time.perf_counter()
    costs = build_objective(layout, weights)
    lower, upper, integrality = _variable_domains(layout)
    a_eq, b_eq = _stack([b for b in blocks if b.sense == "eq"], layout.n_variables)
    a_ub, b_ub = _stack([b for b in blocks if b.sense == "ub"], layout.n_variables)
    timings["assembly"] = time.perf_counter() - started

    return MilpProblem(
        layout=layout,
        costs=costs,
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=a_ub,
        b_ub=b_ub,
        lower_bounds=lower,
        upper_bounds=upper,
        integrality=integrality,
        blocks=blocks,
        build_seconds=timings,
    )


def _variable_domains(layout: VariableLayout) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Границы и целочисленность переменных.

    Окно заявки a_i <= tau_i <= b_i задаётся здесь, а не строками матрицы: границы
    переменной решатели обрабатывают дешевле и точнее, чем эквивалентные неравенства.
    """
    instance = layout.instance
    size = layout.n_variables

    lower = np.zeros(size, dtype=np.float64)
    upper = np.ones(size, dtype=np.float64)
    integrality = np.ones(size, dtype=np.int8)

    for i, request in enumerate(instance.requests):
        column = layout.start_time_column(i)
        lower[column] = float(request.window_start_min)
        upper[column] = float(request.window_end_min)
        integrality[column] = 0

    return lower, upper, integrality


def _stack(blocks: list[ConstraintBlock], n_variables: int) -> tuple[sp.csr_matrix, np.ndarray]:
    if not blocks:
        return sp.csr_matrix((0, n_variables)), np.zeros(0, dtype=np.float64)
    matrix = sp.vstack([block.matrix() for block in blocks], format="csr")
    rhs = np.concatenate([block.rhs() for block in blocks])
    return matrix, rhs
