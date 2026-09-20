from datetime import datetime

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
