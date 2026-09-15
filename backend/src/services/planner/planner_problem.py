"""Описание задачи планирования, не зависящее от решателя.

Здесь только исходные данные: инженеры, заявки, матрицы времени и расстояний, и кому
какую заявку вообще можно отдать. Ни cuOpt, ни MILP сюда не заглядывают — наоборот,
любой решатель читает эту структуру.

Точки задачи пронумерованы одной сквозной нумерацией для всех матриц:
    0 .. число_инженеров-1                   — стартовые точки инженеров
    число_инженеров .. +число_заявок-1       — адреса заявок
    последний номер                          — фиктивный финиш маршрута
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class EngineerSpec:
    engineer_id: int
    name: str
    transport_id: int
    shift_start_min: int  # начало смены, минуты от начала суток
    shift_end_min: int  # конец смены, минуты от начала суток


@dataclass(frozen=True)
class RequestSpec:
    request_id: int
    duration_min: int  # сколько минут занимает работа на месте
    window_start_min: int  # раньше этого времени начинать работу нельзя
    window_end_min: int  # позже этого времени начинать работу нельзя
    skill_id: int
    required_transport_id: int | None  # None — транспорт не важен
    priority_weight: float  # во сколько раз дороже оставить заявку неназначенной


@dataclass
class ProblemInstance:
    engineers: list[EngineerSpec]
    requests: list[RequestSpec]

    # distance_km[транспорт][из_точки][в_точку] — километры
    # travel_min[транспорт][из_точки][в_точку]  — минуты в пути
    #
    # Расстояние зависит от транспорта: пешеход срезает дворами, машина объезжает.
    # Замер на трёх точках в Текстильщиках: пешком 2.62 км, на автомобиле 3.77 км.
    distance_km: dict[int, np.ndarray]
    travel_min: dict[int, np.ndarray]

    # compatible[номер_заявки][номер_инженера] — у инженера есть нужный навык и нужный транспорт
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
        """Сколько всего точек в задаче: старты инженеров, заявки и финиш."""
        return self.n_engineers + self.n_requests + 1

    @property
    def end_node(self) -> int:
        """Номер фиктивного финиша: сюда «приезжают» после последней заявки маршрута."""
        return self.n_engineers + self.n_requests

    def start_node(self, engineer_index: int) -> int:
        """Номер точки, из которой инженер выезжает в начале смены."""
        return engineer_index

    def request_node(self, request_index: int) -> int:
        """Номер точки, где находится заявка."""
        return self.n_engineers + request_index

    def travel_for(self, engineer_index: int, from_node: int, to_node: int) -> int:
        """Сколько минут инженер едет из одной точки задачи в другую.

        Время берётся из матрицы того транспорта, на котором ездит этот инженер:
        между одними и теми же адресами пешком и на машине получается разное время.
        Переезд на фиктивный финиш ничего не стоит — 0 минут.
        """
        if from_node == self.end_node or to_node == self.end_node:
            return 0
        transport_id = self.engineers[engineer_index].transport_id
        return int(self.travel_min[transport_id][from_node][to_node])

    def distance_for(self, engineer_index: int, from_node: int, to_node: int) -> float:
        """Сколько километров инженер проезжает из одной точки задачи в другую.

        Расстояние берётся из матрицы транспорта этого инженера: пешеход срезает
        дворами, машина объезжает, поэтому километры у них тоже разные.
        Переезд на фиктивный финиш ничего не стоит — 0 км.
        """
        if from_node == self.end_node or to_node == self.end_node:
            return 0.0
        transport_id = self.engineers[engineer_index].transport_id
        return float(self.distance_km[transport_id][from_node][to_node])

    def candidates(self, request_index: int) -> list[int]:
        """Номера инженеров, которым эту заявку можно отдать (навык и транспорт подходят)."""
        return np.flatnonzero(self.compatible[request_index]).tolist()

    def unreachable_requests(self) -> list[int]:
        """Номера заявок, которые не подходят ни одному инженеру.

        Причина неназначения у них известна ещё до решателя: ни у кого нет нужного
        навыка или нужного транспорта.
        """
        return np.flatnonzero(~self.compatible.any(axis=1)).tolist()


def build_compatibility(instance: ProblemInstance, engineer_skills: dict[int, set[int]]) -> None:
    """Отмечает, какую заявку какому инженеру вообще можно отдать.

    Подходит, если у инженера есть навык, который требует заявка, и — когда заявка
    требует конкретный транспорт — у инженера именно этот транспорт.

    engineer_skills — навыки по engineer_id, например {1: {1, 2}, 2: {3}}.
    """
    for request_index, request in enumerate(instance.requests):
        for engineer_index, engineer in enumerate(instance.engineers):
            has_skill = request.skill_id in engineer_skills[engineer.engineer_id]
            has_transport = (
                request.required_transport_id is None
                or request.required_transport_id == engineer.transport_id
            )
            instance.compatible[request_index, engineer_index] = has_skill and has_transport
