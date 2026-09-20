from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestEquipmentItem(BaseModel):
    """Сколько штук оборудования одного типа нужно на заявку."""

    model_config = ConfigDict(from_attributes=True)

    equipment_id: int = Field(gt=0)
    quantity: int = Field(default=1, gt=0, le=999)


class RequestWrite(BaseModel):
    """Поля заявки, которые диспетчер заполняет при создании и изменении."""

    model_config = ConfigDict(str_strip_whitespace=True)

    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # длительность работ на месте и навык можно не указывать: они возьмутся из типа работ
    duration_minutes: int | None = Field(default=None, gt=0)
    window_start: datetime
    window_end: datetime
    # не указан — подставится приоритет типа работ (справочник нормативов), его можно сменить
    priority_id: int | None = None
    skill_id: int | None = None
    transport_id: int | None = None  # пусто — транспорт не важен
    work_type_id: int | None = None  # тип работ из справочника нормативов
    # какое оборудование и сколько нужно привезти; пусто — ничего
    equipment: list[RequestEquipmentItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_window(self) -> "RequestWrite":
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError(
                "время окна должно быть с часовым поясом, например 2026-08-17T10:00:00+03:00"
            )
        if self.window_end <= self.window_start:
            raise ValueError("конец окна должен быть позже начала")
        equipment_ids = [item.equipment_id for item in self.equipment]
        if len(set(equipment_ids)) != len(equipment_ids):
            raise ValueError("оборудование не должно повторяться")
        return self


class RequestCreate(RequestWrite):
    # номер из внешней системы; если не указан, база присвоит его сама
    id: int | None = Field(default=None, gt=0)


class RequestRead(RequestWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    office_id: int  # чья заявка; задаётся офисом того, кто её завёл
    # статус меняется не правкой заявки, а переходами (PATCH /requests/status, утверждение плана)
    status_id: int
    # идёт ли заявка в планирование — следует из статуса; для совместимости интерфейса
    is_active: bool
    # утверждённый план, за которым закреплена заявка: из заявки можно перейти в её маршрут
    approved_plan_id: int | None = None
    # отметки разговора с клиентом (docs/algoV2.md, шаг 4): обещанное окно, день, с которого
    # работу перенесли, «требует уточнения» (не дозвонились) и причина отмены
    promised_from: datetime | None = None
    promised_to: datetime | None = None
    moved_from: date | None = None
    needs_followup: bool = False
    cancel_reason: str | None = None


class RequestStatusHistoryItem(BaseModel):
    """Одна смена статуса заявки: из какого в какой, когда, кто, по какому плану."""

    id: int
    changed_at: datetime
    from_status_id: int | None  # None — заявка появилась
    to_status_id: int
    manual: bool  # True — оператор, False — система (утверждение плана)
    user_name: str | None
    plan_id: int | None
    comment: str


class RequestStatusUpdate(BaseModel):
    """Оператор переводит несколько заявок в статус — по таблице ручных переходов."""

    request_ids: list[int] = Field(min_length=1)
    status_id: int


class RequestActivityUpdate(BaseModel):
    """Прежний переключатель «активна»: включить — «Новая», выключить — «Отменена»."""

    request_ids: list[int] = Field(min_length=1)
    is_active: bool


class RequestActivityReport(BaseModel):
    updated: int


class CancelledTransfer(str, Enum):
    """Что делать с отменёнными заявками при переносе дня копией."""

    SKIP = "skip"  # не переносить: в новом дне их никто не отменял
    AS_NEW = "as_new"  # перенести как «Новые»


class RequestImportReport(BaseModel):
    """Итог загрузки CSV: сколько заявок добавлено, обновлено и пропущено."""

    created: int
    updated: int
    # отменённые заявки, которые при переносе дня решили не переносить
    skipped_cancelled: int = 0
