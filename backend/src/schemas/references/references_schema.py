from pydantic import BaseModel, ConfigDict, Field


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PriorityItem(ReferenceItem):
    """Приоритет: level 1 — авария (важнее всего), 2 — подключение, 3 — ремонт и дозаказ."""

    level: int


class WorkTypeItem(ReferenceItem):
    """Тип работ с нормативами: сколько ехать, сколько работать на месте, базовый норматив
    и приоритет, который подставляется новой заявке этого типа."""

    skill_id: int
    priority_id: int
    travel_minutes: int
    work_minutes: int
    baseline_minutes: int


class WorkTypePriorityWrite(BaseModel):
    """Уровень приоритета по умолчанию для типа работ (справочник «Приоритеты»)."""

    priority_id: int


class WorkTypeNormsWrite(BaseModel):
    """Нормативы типа работ, которые правит администратор.

    Влияют только на подстановку по умолчанию: длительность новой заявки при выборе типа
    работ и строки CSV без длительности. У существующих заявок длительность своя.
    """

    travel_minutes: int = Field(ge=0, le=1440)
    work_minutes: int = Field(gt=0, le=1440)


class OfficeItem(ReferenceItem):
    """Офис с координатами: из него выбирают старт исполнителя."""

    address: str
    latitude: float
    longitude: float


class EquipmentItem(ReferenceItem):
    """Тип оборудования: его можно потребовать в заявке."""

    description: str


class RequestStatusItem(ReferenceItem):
    """Статус заявки: code — для кода интерфейса, plannable — идёт ли заявка в расчёт."""

    code: str
    plannable: bool


class RequestStatusTransitionItem(BaseModel):
    """Допустимый переход статуса; manual — делает оператор, иначе — система."""

    model_config = ConfigDict(from_attributes=True)

    from_status_id: int
    to_status_id: int
    manual: bool
    description: str


class ReferencesRead(BaseModel):
    """Все справочники, из которых диспетчер выбирает значения заявок и исполнителей."""

    skills: list[ReferenceItem]
    priorities: list[PriorityItem]
    transports: list[ReferenceItem]
    work_types: list[WorkTypeItem]
    offices: list[OfficeItem] = []
    equipment: list[EquipmentItem] = []
    request_statuses: list[RequestStatusItem] = []
    request_status_transitions: list[RequestStatusTransitionItem] = []
