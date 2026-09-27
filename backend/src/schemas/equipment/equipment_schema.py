from pydantic import BaseModel, ConfigDict, Field


class EquipmentWrite(BaseModel):
    """Поля типа оборудования, которые диспетчер заполняет в справочнике."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    description: str = ""


class EquipmentRead(EquipmentWrite):
    id: int
    # сколько заявок требуют это оборудование и у скольких бригад оно есть:
    # пока хоть одно больше нуля, тип не удалить
    request_count: int = 0
    engineer_count: int = 0


class CapacityRow(BaseModel):
    """Строка справочника ёмкости: сколько штук увозит бригада на этом транспорте."""

    transport_id: int
    transport_name: str = ""
    equipment_id: int
    equipment_name: str = ""
    max_quantity: int = Field(ge=0, le=10000)


class CapacityWrite(BaseModel):
    """Правка справочника: присылаем только изменившиеся пары."""

    rows: list[CapacityRow]


class IssueItem(BaseModel):
    """Одна вещь в выдаче бригаде: сколько нужно по плану, сколько влезет, сколько даём."""

    equipment_id: int
    equipment_name: str = ""
    needed: int = 0  # x0: сумма по заявкам этой бригады в плане
    capacity: int = 0  # предел транспорта из справочника
    current: int = 0  # что у бригады записано сейчас
    recommended: int = 0  # min(предел, x0 + запас)


class IssueBrigade(BaseModel):
    """Строка выдачи: бригада, её транспорт и что ей предлагается взять."""

    engineer_id: int
    name: str
    transport_id: int
    transport_name: str = ""
    requests: int = 0  # сколько заявок у неё в плане — по ним и считался x0
    items: list[IssueItem]


class IssuePreview(BaseModel):
    """Рекомендуемая выдача по плану: её диспетчер правит и утверждает."""

    plan_id: int
    reserve: int  # общий запас сверх потребности плана (настройка системы)
    brigades: list[IssueBrigade]


class IssueQuantity(BaseModel):
    equipment_id: int
    quantity: int = Field(ge=0, le=10000)


class IssueBrigadeWrite(BaseModel):
    engineer_id: int
    items: list[IssueQuantity]


class IssueWrite(BaseModel):
    """Утверждение выдачи: что диспетчер решил выдать бригадам."""

    brigades: list[IssueBrigadeWrite]


class IssueDone(BaseModel):
    """Итог утверждения: скольким бригадам и сколько штук записали."""

    brigades: int
    items: int
