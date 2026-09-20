from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SystemTimeRead(BaseModel):
    """Системное время: что показываем на часах и насколько оно перемотано."""

    now: datetime  # системное время с учётом сдвига
    real_now: datetime  # настоящее время сервера
    offset_seconds: int
    updated_at: datetime | None = None
    updated_by: str | None = None  # кто перематывал


class SystemTimeWrite(BaseModel):
    """Перемотка: либо на какой момент поставить часы, либо сдвиг в секундах."""

    model_config = ConfigDict(extra="forbid")

    now: datetime | None = None
    offset_seconds: int | None = None


class ServiceStatus(BaseModel):
    """Состояние соседней службы: отвечает ли и что именно ответила."""

    name: str
    target: str  # адрес или строка подключения без пароля
    ok: bool
    detail: str


class SystemInfo(BaseModel):
    """Параметры системы для отдельной вкладки: версии, подключения, настройки, объёмы."""

    app_name: str
    version: str
    python_version: str
    time: SystemTimeRead
    services: list[ServiceStatus]
    settings: dict[str, str]
    data: dict[str, int]


class PlanRunEventRead(BaseModel):
    """Одна строка хода расчёта: что считалось и когда (db/init/038)."""

    model_config = ConfigDict(from_attributes=True)

    at: datetime
    level: str
    step: str
    message: str
    progress: int | None = None


class PlanRunRead(BaseModel):
    """Запуск расчёта: чем считали, на каком шаге и чем кончилось."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_date: date | None
    kind: str  # build / replan / preview
    solver: str | None
    status: str  # running / done / failed
    step: str
    progress: int
    plan_id: int | None
    error: str | None
    user_name: str | None = None
    started_at: datetime
    finished_at: datetime | None
    # сколько заняло, секунд: у незаконченного — сколько идёт прямо сейчас
    duration_seconds: float
    events: list[PlanRunEventRead] = []
