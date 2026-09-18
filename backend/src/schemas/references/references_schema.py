from pydantic import BaseModel, ConfigDict, Field


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


class ReferencesRead(BaseModel):
    """Все справочники, из которых диспетчер выбирает значения заявок и исполнителей."""

    skills: list[ReferenceItem]
    priorities: list[ReferenceItem]
    transports: list[ReferenceItem]
    work_types: list[WorkTypeItem]
    offices: list[OfficeItem] = []
    equipment: list[EquipmentItem] = []
