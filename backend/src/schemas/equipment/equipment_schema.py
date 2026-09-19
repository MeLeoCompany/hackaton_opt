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
