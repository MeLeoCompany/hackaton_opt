from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EngineerEquipmentItem(BaseModel):
    """Сколько штук оборудования одного типа везёт бригада."""

    equipment_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=999)


class EngineerWrite(BaseModel):
    """Поля исполнителя, которые диспетчер заполняет при создании и изменении."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    start_latitude: float = Field(ge=-90, le=90)
    start_longitude: float = Field(ge=-180, le=180)
    shift_start: datetime
    shift_end: datetime
    transport_id: int
    # выезжает из своего офиса: старт ставится в точку офиса, координаты из запроса не нужны
    start_at_office: bool = False
    # по ТЗ у исполнителя от 1 до 3 навыков
    skill_ids: list[int] = Field(min_length=1, max_length=3)
    # оборудование, которое бригада везёт с собой; пусто — ничего
    equipment: list[EngineerEquipmentItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_shift_and_skills(self) -> "EngineerWrite":
        if self.shift_start.tzinfo is None or self.shift_end.tzinfo is None:
            raise ValueError(
                "время смены должно быть с часовым поясом, например 2026-08-17T09:00:00+03:00"
            )
        if self.shift_end <= self.shift_start:
            raise ValueError("конец смены должен быть позже начала")
        equipment_ids = [item.equipment_id for item in self.equipment]
        if len(set(equipment_ids)) != len(equipment_ids):
            raise ValueError("оборудование не должно повторяться")
        if len(set(self.skill_ids)) != len(self.skill_ids):
            raise ValueError("навыки не должны повторяться")
        return self


class EngineerCreate(EngineerWrite):
    # номер можно не указывать — база присвоит сама
    id: int | None = Field(default=None, gt=0)


class EngineerRead(EngineerWrite):
    id: int
    office_id: int  # чья бригада; задаётся офисом того, кто её завёл


class EngineerImportReport(BaseModel):
    """Итог загрузки CSV: сколько исполнителей добавлено и сколько обновлено."""

    created: int
    updated: int
