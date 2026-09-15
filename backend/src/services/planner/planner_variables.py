"""Раздел 3 постановки: раскладка переменных в один вектор x.

Порядок блоков фиксирован и является контрактом для всех строителей ограничений:

    [ x^k_uv ][ y^k_i ][ u_k ][ z_i ][ tau_i ]
      дуги     назнач.  занят  не назн.  время начала работ

Отличие от исходной постановки: время начала работ хранится как tau_i (одна переменная
на заявку), а не tau^k_i. Заявку обслуживает не более одного инженера, поэтому индекс по
инженеру избыточен: он множит число непрерывных переменных на |E|, ничего не добавляя.
"""

from dataclasses import dataclass, field

import numpy as np

from src.services.planner.planner_problem import ProblemInstance


@dataclass
class VariableLayout:
    instance: ProblemInstance

    # параллельные массивы по дугам: кто едет, откуда, куда
    arc_engineer: np.ndarray = field(init=False)
    arc_from: np.ndarray = field(init=False)
    arc_to: np.ndarray = field(init=False)

    # (engineer_index, request_index) -> столбец в блоке y
    assign_index: dict[tuple[int, int], int] = field(init=False)

    def __post_init__(self) -> None:
        self._build_arcs()
        self._build_assignments()

    # ---- построение ----------------------------------------------------

    def _build_arcs(self) -> None:
        engineers: list[int] = []
        sources: list[int] = []
        targets: list[int] = []

        for k in range(self.instance.n_engineers):
            served = [i for i in range(self.instance.n_requests) if self.instance.compatible[i, k]]

            for i in served:
                if self._start_arc_possible(k, i):
                    engineers.append(k)
                    sources.append(self.instance.start_node(k))
                    targets.append(self.instance.request_node(i))

            for i in served:
                for j in served:
                    if i == j or not self._inter_arc_possible(k, i, j):
                        continue
                    engineers.append(k)
                    sources.append(self.instance.request_node(i))
                    targets.append(self.instance.request_node(j))

            # выезд в фиктивный финиш: маршрут обрывается на последней заявке
            for i in served:
                engineers.append(k)
                sources.append(self.instance.request_node(i))
                targets.append(self.instance.end_node)

        self.arc_engineer = np.array(engineers, dtype=np.int32)
        self.arc_from = np.array(sources, dtype=np.int32)
        self.arc_to = np.array(targets, dtype=np.int32)

    def _start_arc_possible(self, k: int, i: int) -> bool:
        """Инженер физически успевает доехать от своего старта к заявке в её окно."""
        engineer = self.instance.engineers[k]
        request = self.instance.requests[i]
        travel = self.instance.travel_for(k, self.instance.start_node(k), self.instance.request_node(i))
        earliest = max(engineer.shift_start_min + travel, request.window_start_min)
        return earliest <= request.window_end_min and earliest + request.duration_min <= engineer.shift_end_min

    def _inter_arc_possible(self, k: int, i: int, j: int) -> bool:
        """Отсечение по времени: из окна i при всём желании не попасть в окно j.

        На реальных данных окна дискретны (шесть двухчасовых слотов), поэтому такое
        отсечение убирает основную массу дуг: заявка из слота 20-22 не может
        предшествовать заявке из слота 10-12.
        """
        source = self.instance.requests[i]
        target = self.instance.requests[j]
        travel = self.instance.travel_for(
            k, self.instance.request_node(i), self.instance.request_node(j)
        )
        return source.window_start_min + source.duration_min + travel <= target.window_end_min

    def _build_assignments(self) -> None:
        self.assign_index = {}
        column = 0
        for k in range(self.instance.n_engineers):
            for i in range(self.instance.n_requests):
                if self.instance.compatible[i, k]:
                    self.assign_index[(k, i)] = column
                    column += 1

    # ---- размеры блоков ------------------------------------------------

    @property
    def n_arcs(self) -> int:
        return int(self.arc_engineer.size)

    @property
    def n_assignments(self) -> int:
        return len(self.assign_index)

    @property
    def n_variables(self) -> int:
        return (
            self.n_arcs
            + self.n_assignments
            + self.instance.n_engineers
            + self.instance.n_requests
            + self.instance.n_requests
        )

    # ---- смещения блоков -----------------------------------------------

    @property
    def arc_offset(self) -> int:
        return 0

    @property
    def assign_offset(self) -> int:
        return self.n_arcs

    @property
    def usage_offset(self) -> int:
        return self.assign_offset + self.n_assignments

    @property
    def unassigned_offset(self) -> int:
        return self.usage_offset + self.instance.n_engineers

    @property
    def start_time_offset(self) -> int:
        return self.unassigned_offset + self.instance.n_requests

    # ---- адреса переменных ---------------------------------------------

    def arc_column(self, arc: int) -> int:
        return self.arc_offset + arc

    def assign_column(self, engineer_index: int, request_index: int) -> int:
        return self.assign_offset + self.assign_index[(engineer_index, request_index)]

    def usage_column(self, engineer_index: int) -> int:
        return self.usage_offset + engineer_index

    def unassigned_column(self, request_index: int) -> int:
        return self.unassigned_offset + request_index

    def start_time_column(self, request_index: int) -> int:
        return self.start_time_offset + request_index

    # ---- выборки дуг ---------------------------------------------------

    def arcs_into(self, node: int, engineer_index: int) -> np.ndarray:
        return np.flatnonzero((self.arc_to == node) & (self.arc_engineer == engineer_index))

    def arcs_out_of(self, node: int, engineer_index: int) -> np.ndarray:
        return np.flatnonzero((self.arc_from == node) & (self.arc_engineer == engineer_index))
