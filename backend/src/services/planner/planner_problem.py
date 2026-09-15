"""Солвер-независимое описание задачи планирования.

Здесь нет ничего, что знало бы про cuOpt, MILP или эвристику: только множества,
параметры и матрицы из раздела 1-2 постановки. Любой решатель — потребитель этой
структуры, а не наоборот.

Узлы задачи (единая индексация для всех матриц):
    0 .. n_engineers-1                        — стартовые точки инженеров
    n_engineers .. n_engineers+n_requests-1   — точки заявок
    n_engineers+n_requests                    — фиктивный финиш (см. flow_constraint)
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class EngineerSpec:
    engineer_id: int
    name: str
    transport_id: int
    shift_start_min: int
    shift_end_min: int


@dataclass(frozen=True)
class RequestSpec:
    request_id: int
    duration_min: int
    window_start_min: int
    window_end_min: int
    skill_id: int
    required_transport_id: int | None
    priority_weight: float


@dataclass
class ProblemInstance:
    engineers: list[EngineerSpec]
    requests: list[RequestSpec]

    # distance_km[transport_id][u][v] — км, travel_min[transport_id][u][v] — целые минуты.
    #
    # Расстояние тоже зависит от транспорта, вопреки исходному допущению постановки:
    # у реального роутера пешеход срезает дворами, а машина объезжает. Замер на трёх
    # точках в Текстильщиках: пешком 2.62 км, на автомобиле 3.77 км — разница 44%.
    # Общая матрица расстояний исказила бы пробег, а это оценочная метрика ТЗ.
    distance_km: dict[int, np.ndarray]
    travel_min: dict[int, np.ndarray]

    # compatible[i][k] — заявку i вообще допустимо отдать инженеру k (навык И транспорт)
    compatible: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.compatible = np.zeros((self.n_requests, self.n_engineers), dtype=bool)

    @property
    def n_engineers(self) -> int:
        return len(self.engineers)

    @property
    def n_requests(self) -> int:
        return len(self.requests)

    @property
    def n_nodes(self) -> int:
        """Старты инженеров + заявки + фиктивный финиш."""
        return self.n_engineers + self.n_requests + 1

    @property
    def end_node(self) -> int:
        return self.n_engineers + self.n_requests

    def start_node(self, engineer_index: int) -> int:
        return engineer_index

    def request_node(self, request_index: int) -> int:
        return self.n_engineers + request_index

    def travel_for(self, engineer_index: int, u: int, v: int) -> int:
        """Время в пути для конкретного инженера: зависит от его типа транспорта."""
        if u == self.end_node or v == self.end_node:
            return 0
        transport_id = self.engineers[engineer_index].transport_id
        return int(self.travel_min[transport_id][u][v])

    def distance_for(self, engineer_index: int, u: int, v: int) -> float:
        if u == self.end_node or v == self.end_node:
            return 0.0
        transport_id = self.engineers[engineer_index].transport_id
        return float(self.distance_km[transport_id][u][v])

    def candidates(self, request_index: int) -> list[int]:
        return np.flatnonzero(self.compatible[request_index]).tolist()

    def unreachable_requests(self) -> list[int]:
        """Заявки, у которых нет ни одного совместимого инженера (E_i = пусто).

        Их незачем передавать решателю — причина неназначения известна заранее.
        """
        return np.flatnonzero(~self.compatible.any(axis=1)).tolist()


def build_compatibility(
    instance: ProblemInstance, engineer_skills: dict[int, set[int]]
) -> None:
    """Раздел 4.1: квалификация и ресурс. Считается до решателя.

    engineer_skills — навыки по engineer_id (не по индексу).
    """
    for i, request in enumerate(instance.requests):
        for k, engineer in enumerate(instance.engineers):
            has_skill = request.skill_id in engineer_skills[engineer.engineer_id]
            has_transport = (
                request.required_transport_id is None
                or request.required_transport_id == engineer.transport_id
            )
            instance.compatible[i, k] = has_skill and has_transport
