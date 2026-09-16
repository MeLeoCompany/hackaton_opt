from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestWrite(BaseModel):
    """Поля заявки, которые диспетчер заполняет при создании и изменении."""

    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # длительность работ на месте и навык можно не указывать: они возьмутся из типа работ
    duration_minutes: int | None = Field(default=None, gt=0)
    window_start: datetime
    window_end: datetime
    priority_id: int
    skill_id: int | None = None
    transport_id: int | None = None  # пусто — транспорт не важен
    work_type_id: int | None = None  # тип работ из справочника нормативов
    is_active: bool = True  # выключенная заявка не попадает в сборку задачи планирования

    @model_validator(mode="after")
    def check_window(self) -> "RequestWrite":
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("время окна должно быть с часовым поясом, например 2026-08-17T10:00:00+03:00")
        if self.window_end <= self.window_start:
            raise ValueError("конец окна должен быть позже начала")
        return self


class RequestCreate(RequestWrite):
    # номер из внешней системы; если не указан, база присвоит его сама
    id: int | None = Field(default=None, gt=0)


class RequestRead(RequestWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RequestActivityUpdate(BaseModel):
    """Включить или выключить сразу несколько заявок для планирования."""

    request_ids: list[int] = Field(min_length=1)
    is_active: bool


class RequestActivityReport(BaseModel):
    updated: int


class RequestImportReport(BaseModel):
    """Итог загрузки CSV: сколько заявок добавлено и сколько обновлено."""

    created: int
    updated: int
