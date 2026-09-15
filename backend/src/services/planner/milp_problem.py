"""Задача MILP, которую шаг за шагом наполняют модули сборки.

Запись задачи:
    минимизировать   costs · значения_переменных
    при условии      A · значения_переменных  (signs)  b
                     lower_bounds <= значения_переменных <= upper_bounds
                     переменные с is_integer = 1 принимают только целые значения

Один столбец A — одна переменная, одна строка A — одно ограничение.
"""

from collections import defaultdict

import numpy as np
import scipy.sparse as sp


class MilpProblem:
    def __init__(self) -> None:
        # ---- переменные (столбцы A) ----
        self.costs: list[float] = []  # сколько стоит единица переменной в целевой функции
        self.lower_bounds: list[float] = []
        self.upper_bounds: list[float] = []
        self.is_integer: list[int] = []  # 1 — только целые значения, 0 — любые

        # ---- номер столбца по смыслу переменной ----
        # «инженер едет из одной точки задачи прямо в другую», 0 или 1
        self.drive_column: dict[tuple[int, int, int], int] = {}  # (инженер, из_точки, в_точку)
        # «заявка назначена инженеру», 0 или 1
        self.assigned_column: dict[tuple[int, int], int] = {}  # (инженер, заявка)
        # «у инженера есть хотя бы одна заявка», 0 или 1
        self.engineer_used_column: dict[int, int] = {}  # инженер
        # «заявка никому не назначена», 0 или 1
        self.unassigned_column: dict[int, int] = {}  # заявка
        # «во сколько начинается работа по заявке», минуты от начала суток
        self.work_start_column: dict[int, int] = {}  # заявка

        # столбцы переездов, которые выходят из точки / входят в точку, по каждому инженеру
        self.drives_out_of: dict[tuple[int, int], list[int]] = defaultdict(list)  # (инженер, точка)
        self.drives_into: dict[tuple[int, int], list[int]] = defaultdict(list)  # (инженер, точка)

        # ---- ограничения (строки A) копятся тройками (строка, столбец, коэффициент) ----
        self._row_numbers: list[int] = []
        self._column_numbers: list[int] = []
        self._coefficients: list[float] = []
        self.b: list[float] = []  # правая часть строки
        self.signs: list[str] = []  # знак строки: "=" или "<="

        self.A: sp.csr_matrix | None = None
        self.timings: dict[str, float] = {}  # сколько секунд занял каждый шаг сборки

    @property
    def n_variables(self) -> int:
        return len(self.costs)

    @property
    def n_rows(self) -> int:
        return len(self.b)

    def add_variable(self, lower_bound: float, upper_bound: float, is_integer: bool) -> int:
        """Заводит новую переменную и возвращает номер её столбца в A."""
        self.costs.append(0.0)
        self.lower_bounds.append(lower_bound)
        self.upper_bounds.append(upper_bound)
        self.is_integer.append(1 if is_integer else 0)
        return self.n_variables - 1

    def add_drive(self, engineer_index: int, from_node: int, to_node: int) -> None:
        """Заводит переменную «инженер едет из from_node прямо в to_node» (0 или 1)."""
        column = self.add_variable(0.0, 1.0, is_integer=True)
        self.drive_column[(engineer_index, from_node, to_node)] = column
        self.drives_out_of[(engineer_index, from_node)].append(column)
        self.drives_into[(engineer_index, to_node)].append(column)

    def add_row(self, coefficients: list[tuple[int, float]], sign: str, right_side: float) -> None:
        """Добавляет ограничение:  сумма(коэффициент · переменная)  sign  right_side.

        coefficients — пары (номер столбца, коэффициент); переменные, которых нет в списке,
        входят в строку с нулём.
        """
        row_number = self.n_rows
        for column, coefficient in coefficients:
            self._row_numbers.append(row_number)
            self._column_numbers.append(column)
            self._coefficients.append(coefficient)
        self.b.append(right_side)
        self.signs.append(sign)

    def finalize(self) -> None:
        """Превращает накопленные списки в numpy-массивы и собирает разреженную матрицу A."""
        self.A = sp.csr_matrix(
            (self._coefficients, (self._row_numbers, self._column_numbers)),
            shape=(self.n_rows, self.n_variables),
        )
        self.costs = np.array(self.costs)
        self.lower_bounds = np.array(self.lower_bounds)
        self.upper_bounds = np.array(self.upper_bounds)
        self.is_integer = np.array(self.is_integer, dtype=np.int8)
        self.b = np.array(self.b)
        self.signs = np.array(self.signs)
