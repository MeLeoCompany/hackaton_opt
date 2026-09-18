from pydantic import BaseModel, ConfigDict


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class WorkTypeItem(ReferenceItem):
    """Тип работ с нормативами: сколько ехать, сколько работать на месте, базовый норматив."""

    skill_id: int
    travel_minutes: int
    work_minutes: int
    baseline_minutes: int


class OfficeItem(ReferenceItem):
    """Офис с координатами: из него выбирают старт исполнителя."""

    address: str
    latitude: float
    longitude: float


class EquipmentItem(ReferenceItem):
    """Тип оборудования: его можно потребовать в заявке."""

    description: str


class ReferencesRead(BaseModel):
    """Все справочники, из которых диспетчер выбирает значения заявок и исполнителей."""

    skills: list[ReferenceItem]
    priorities: list[ReferenceItem]
    transports: list[ReferenceItem]
    work_types: list[WorkTypeItem]
    offices: list[OfficeItem] = []
    equipment: list[EquipmentItem] = []
