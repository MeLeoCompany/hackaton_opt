"""Задача планирования на день в виде, не зависящем от решателя.

Здесь только исходные данные: исполнители, заявки, матрицы времени и расстояний, и кому
какую заявку вообще можно отдать. Загружает её planner_loader, решает cuopt_solver.

Точки задачи пронумерованы одной сквозной нумерацией для всех матриц:
    0 .. число_исполнителей-1              — стартовые точки исполнителей
    число_исполнителей .. +число_заявок-1   — адреса заявок
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class EngineerSpec:
    engineer_id: int
    name: str
    transport_id: int
    shift_start_min: int  # начало смены, минуты от начала дня
    shift_end_min: int  # конец смены, минуты от начала дня
    # сколько единиц каждого оборудования доступно бригаде на остаток смены
    equipment_capacity: dict[int, int] = field(default_factory=dict)


# уровни приоритета: 1 — авария, 2 — подключение, 3 — ремонт и дозаказ (db/init/032)
TOP_PRIORITY_LEVEL = 1
LOWEST_PRIORITY_LEVEL = 3
# уровни выше базового: по ним в целевой функции идут отдельные ступени
PRIORITY_LEVELS = (1, 2)

# Ярусы целевой функции (docs/algoV2.md): чем меньше номер, тем важнее класс заявок.
# Каждый ярус сильнее всех нижних вместе взятых, поэтому одна авария важнее любого числа
# подключений, а обещанная клиенту заявка — любого числа обычных
RANK_EMERGENCY = 1  # P1, авария
RANK_PROMISED = 2  # «согласовано»: обещание клиенту, подвинуть может только авария
RANK_MOVED_HIGH = 3  # P2 с отметкой «перенесена»
RANK_MOVED_NORMAL = 4  # P3 с отметкой «перенесена»
RANK_HIGH = 5  # P2
RANK_NORMAL = 6  # P3 — базовый ярус, отдельной ступени не получает
# во втором расчёте раскрытые заявки идут ниже тех, что уже влезли в первый (ярус C1)
WIDENED_RANK_SHIFT = 10


def round_ranks(requests, kept_request_ids: set[int]) -> dict[int, int]:
    """Ярусы второго и третьего расчётов круга (docs/algoV2.md, шаги 3 и 5).

    A — аварии, откуда бы ни были: авария вправе подвинуть обычную заявку;
    B — все, кто влез в первый расчёт;
    C — раскрытые, то есть те, по кому звонили.
    Внутри ярусов порядок обычный (обещание, перенос, приоритет), поэтому согласованная
    заявка идёт первой среди раскрытых. Ярусы считаются на каждый запуск и не сохраняются:
    следующий круг снова начинается с настоящих приоритетов.
    """
    ranks = {}
    for index, request in enumerate(requests):
        if request.priority_level == TOP_PRIORITY_LEVEL:
            ranks[index] = RANK_EMERGENCY
        elif request.request_id in kept_request_ids:
            ranks[index] = request.objective_rank
        else:
            ranks[index] = request.objective_rank + WIDENED_RANK_SHIFT
    return ranks


@dataclass(frozen=True)
class RequestSpec:
    request_id: int
    duration_min: int  # сколько минут занимает работа на месте
    window_start_min: int  # раньше этого времени начинать работу нельзя
    window_end_min: int  # позже этого времени начинать работу нельзя
    skill_id: int
    required_transport_id: int | None  # None — транспорт не важен
    # уровень приоритета из справочника: 1 — авария, 2 — подключение, 3 — ремонт и дозаказ.
    # Оптимизатор берёт заявки по уровням: сначала все аварии, потом подключения, потом остальное
    priority_level: int = LOWEST_PRIORITY_LEVEL
    # отметки заявки: обещана клиенту по телефону и переносилась с другого дня
    promised: bool = False
    moved: bool = False
    # сколько единиц каждого оборудования останется у клиента после выполнения заявки
    equipment_demand: dict[int, int] = field(default_factory=dict)

    @property
    def is_urgent(self) -> bool:
        """Авария — верхний уровень приоритета."""
        return self.priority_level == TOP_PRIORITY_LEVEL

    @property
    def objective_rank(self) -> int:
        """Ярус заявки в целевой функции: авария, обещание, перенос, приоритет."""
        if self.priority_level == TOP_PRIORITY_LEVEL:
            return RANK_EMERGENCY
        if self.promised:
            return RANK_PROMISED
        high = self.priority_level < LOWEST_PRIORITY_LEVEL
        if self.moved:
            return RANK_MOVED_HIGH if high else RANK_MOVED_NORMAL
        return RANK_HIGH if high else RANK_NORMAL


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

    # compatible[номер_заявки][номер_исполнителя] — у исполнителя есть нужный навык и нужный транспорт
    compatible: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.compatible = np.zeros((self.n_requests, self.n_engineers), dtype=bool)

    @property
    def n_engineers(self) -> int:
        return len(self.engineers)

    @property
    def n_requests(self) -> int:
        return len(self.requests)

    def start_node(self, engineer_index: int) -> int:
        """Номер точки, из которой исполнитель выезжает в начале смены."""
        return engineer_index

    def request_node(self, request_index: int) -> int:
        """Номер точки, где находится заявка."""
        return self.n_engineers + request_index

    def candidates(self, request_index: int) -> list[int]:
        """Номера исполнителей, которым подходит заявка по статическим ограничениям."""
        return np.flatnonzero(self.compatible[request_index]).tolist()

    def route_equipment_usage(self, request_indices: list[int]) -> dict[int, int]:
        """Суммарный расход оборудования заявками одного маршрута."""
        usage: dict[int, int] = {}
        for request_index in request_indices:
            for equipment_id, quantity in self.requests[request_index].equipment_demand.items():
                usage[equipment_id] = usage.get(equipment_id, 0) + quantity
        return usage

    def route_fits_equipment(self, engineer_index: int, request_indices: list[int]) -> bool:
        capacity = self.engineers[engineer_index].equipment_capacity
        return all(
            quantity <= capacity.get(equipment_id, 0)
            for equipment_id, quantity in self.route_equipment_usage(request_indices).items()
        )


def build_compatibility(instance: ProblemInstance, engineer_skills: dict[int, set[int]]) -> None:
    """Отмечает, какую заявку какому исполнителю вообще можно отдать.

    Подходит, если у исполнителя есть навык, который требует заявка, и — когда заявка
    требует конкретный транспорт — у исполнителя именно этот транспорт.

    engineer_skills — навыки по engineer_id, например {1: {1, 2}, 2: {3}}.
    """
    for request_index, request in enumerate(instance.requests):
        for engineer_index, engineer in enumerate(instance.engineers):
            has_skill = request.skill_id in engineer_skills[engineer.engineer_id]
            has_transport = (
                request.required_transport_id is None
                or request.required_transport_id == engineer.transport_id
            )
            has_equipment = all(
                quantity <= engineer.equipment_capacity.get(equipment_id, 0)
                for equipment_id, quantity in request.equipment_demand.items()
            )
            instance.compatible[request_index, engineer_index] = (
                has_skill and has_transport and has_equipment
            )
