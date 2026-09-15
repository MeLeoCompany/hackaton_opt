"""Общий контейнер для блока ограничений.

Каждый раздел постановки строит свой блок независимо; сборка в матрицы A_eq/A_ub
происходит один раз в planner_milp. Копим тройки (строка, столбец, коэффициент) —
плотную матрицу на наших размерах собирать нельзя.
"""

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp


@dataclass
class ConstraintBlock:
    label: str
    sense: str  # "eq" или "ub"
    n_variables: int

    _rows: list[int] = field(default_factory=list, repr=False)
    _cols: list[int] = field(default_factory=list, repr=False)
    _vals: list[float] = field(default_factory=list, repr=False)
    _rhs: list[float] = field(default_factory=list, repr=False)
    _row_labels: list[str] = field(default_factory=list, repr=False)

    def add_row(self, terms: dict[int, float], rhs: float, label: str = "") -> None:
        row = len(self._rhs)
        for column, coefficient in terms.items():
            if coefficient == 0.0:
                continue
            self._rows.append(row)
            self._cols.append(column)
            self._vals.append(coefficient)
        self._rhs.append(rhs)
        self._row_labels.append(label)

    @property
    def n_rows(self) -> int:
        return len(self._rhs)

    @property
    def n_nonzeros(self) -> int:
        return len(self._vals)

    @property
    def row_labels(self) -> list[str]:
        return self._row_labels

    def matrix(self) -> sp.csr_matrix:
        return sp.coo_matrix(
            (self._vals, (self._rows, self._cols)),
            shape=(self.n_rows, self.n_variables),
            dtype=np.float64,
        ).tocsr()

    def rhs(self) -> np.ndarray:
        return np.asarray(self._rhs, dtype=np.float64)
