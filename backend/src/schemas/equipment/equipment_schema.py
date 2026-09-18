from pydantic import BaseModel, ConfigDict, Field


class EquipmentWrite(BaseModel):
    """Поля типа оборудования, которые диспетчер заполняет в справочнике."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    description: str = ""


class EquipmentRead(EquipmentWrite):
    id: int
    # сколько заявок требуют это оборудование: пока их больше нуля, тип не удалить
    request_count: int = 0
