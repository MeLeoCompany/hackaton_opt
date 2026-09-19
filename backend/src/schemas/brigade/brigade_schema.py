from datetime import date, datetime

from pydantic import BaseModel, Field


class BrigadeEquipment(BaseModel):
    name: str
    quantity: int


class BrigadeVisit(BaseModel):
    """Заявка маршрута бригады — как её видит бригада в телефоне."""

    request_id: int
    visit_order: int
    address: str
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    planned_arrival_time: datetime  # по плану — начало работ
    duration_minutes: int
    work_type: str | None
    priority: str
    # уровень приоритета: 1 аварийный, 2 высокий, 3 обычный
    priority_level: int
    equipment: list[BrigadeEquipment]
    status_id: int
    status_code: str
    status_name: str
    # заявку сняли с плана (вернули в «Новая») — бригада к ней больше не едет
    removed: bool = False
    departed_at: datetime | None = None
    arrived_at: datetime | None = None
    finished_at: datetime | None = None


class BrigadeRoute(BaseModel):
    """Маршрут бригады на день из утверждённого плана; plan_id None — маршрута нет."""

    plan_date: date
    brigade_name: str
    plan_id: int | None = None
    shift_start: datetime | None = None
    shift_end: datetime | None = None
    # откуда бригада выезжает на первую заявку — для маршрута в картах
    start_latitude: float | None = None
    start_longitude: float | None = None
    visits: list[BrigadeVisit] = []


class BrigadeDays(BaseModel):
    """Дни с маршрутом у бригады и какой открыть: сегодня, иначе ближайший.

    Дней нет — открывается сегодняшний, чтобы в приложении была видна дата.
    """

    days: list[date]
    default_day: date | None


class BrigadeFailure(BaseModel):
    """Бригада не может выполнить заявку — почему."""

    reason: str = Field(min_length=1, max_length=500)
