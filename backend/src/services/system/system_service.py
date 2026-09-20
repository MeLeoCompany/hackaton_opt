"""Системное время и параметры системы.

Время сервера можно перемотать вперёд для демонстрации: тогда пересчёт плана «с текущего
момента», отметки бригад и расчёт опозданий считают «сейчас» сдвинутым. Сдвиг хранится
в базе (034) и держится в памяти процесса (`core/clock.py`).
"""

import platform
import sys
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.config import settings
from src.core.errors import DataError
from src.models import AppUser, Brigade, Engineer, Office, Plan, Request
from src.repositories.system import system_repository
from src.schemas.system import ServiceStatus, SystemInfo, SystemTimeRead, SystemTimeWrite

APP_VERSION = "0.1.0"
# перемотка — инструмент демонстрации: назад дальше суток и вперёд дальше года смысла не имеет
MIN_OFFSET_SECONDS = -24 * 3600
MAX_OFFSET_SECONDS = 366 * 24 * 3600


class SystemTimeError(DataError):
    """Сдвиг времени вне разумных границ."""


async def load_offset(session: AsyncSession) -> None:
    """При старте приложения поднимаем сохранённый сдвиг в память."""
    row = await system_repository.get_system_time(session)
    clock.set_offset(timedelta(seconds=row.offset_seconds))


async def read_time(session: AsyncSession) -> SystemTimeRead:
    row = await system_repository.get_system_time(session)
    clock.set_offset(timedelta(seconds=row.offset_seconds))
    user = await session.get(AppUser, row.updated_by) if row.updated_by else None
    return SystemTimeRead(
        now=clock.now(),
        real_now=clock.real_now(),
        offset_seconds=row.offset_seconds,
        updated_at=row.updated_at if row.offset_seconds else None,
        updated_by=user.name if user else None,
    )


async def set_time(
    session: AsyncSession, payload: SystemTimeWrite, user_id: int | None = None
) -> SystemTimeRead:
    """Ставит часы на момент (`now`) или задаёт сдвиг в секундах; 0 — вернуть настоящее время."""
    if (payload.now is None) == (payload.offset_seconds is None):
        raise SystemTimeError(["укажите либо время (now), либо сдвиг в секундах"])
    if payload.now is not None:
        moment = payload.now if payload.now.tzinfo else payload.now.replace(tzinfo=UTC)
        seconds = round((moment - clock.real_now()).total_seconds())
    else:
        seconds = payload.offset_seconds
    if not MIN_OFFSET_SECONDS <= seconds <= MAX_OFFSET_SECONDS:
        raise SystemTimeError(["перематывать можно не больше чем на сутки назад и на год вперёд"])

    row = await system_repository.get_system_time(session)
    row.offset_seconds = seconds
    row.updated_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.commit()
    clock.set_offset(timedelta(seconds=seconds))
    return await read_time(session)


def hidden_password(url: str) -> str:
    """Строка подключения без пароля: показываем её на странице параметров."""
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, address = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{address}"


async def check_service(name: str, url: str, path: str) -> ServiceStatus:
    """Отвечает ли соседняя служба: Valhalla, R5."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{url}{path}")
        ok = response.status_code == 200
        detail = "отвечает" if ok else f"ответила {response.status_code}"
    except httpx.HTTPError as error:
        ok, detail = False, f"недоступна: {type(error).__name__}"
    return ServiceStatus(name=name, target=url, ok=ok, detail=detail)


async def check_database(session: AsyncSession) -> ServiceStatus:
    try:
        version = (await session.execute(text("SHOW server_version"))).scalar_one()
        ok, detail = True, f"PostgreSQL {version}"
    except Exception as error:  # noqa: BLE001 — на странице параметров важно показать причину
        ok, detail = False, f"недоступна: {type(error).__name__}"
    return ServiceStatus(
        name="База данных",
        target=hidden_password(settings.database_url),
        ok=ok,
        detail=detail,
    )


def check_solver() -> ServiceStatus:
    """cuOpt живёт внутри бэкенда: проверяем, что пакет на месте."""
    try:
        # импорт по требованию: пакета может не быть
        import cuopt

        detail = f"установлен, версия {getattr(cuopt, '__version__', 'неизвестна')}"
        ok = True
    except ImportError:
        ok, detail = False, "не установлен — доступен только базовый алгоритм"
    return ServiceStatus(name="Решатель cuOpt", target="в процессе бэкенда", ok=ok, detail=detail)


async def read_info(session: AsyncSession) -> SystemInfo:
    """Всё, что показывает вкладка «Система»."""
    services = [
        await check_database(session),
        await check_service("Маршрутизатор Valhalla", settings.valhalla_url, "/status"),
        await check_service("Общественный транспорт R5", settings.r5_url, "/health"),
        check_solver(),
    ]
    data = await system_repository.counts(
        session,
        {
            "Офисы": Office,
            "Бригады": Brigade,
            "Смены": Engineer,
            "Заявки": Request,
            "Планы": Plan,
            "Учётки": AppUser,
        },
    )
    return SystemInfo(
        app_name=settings.app_name,
        version=APP_VERSION,
        python_version=platform.python_version() + f" ({sys.platform})",
        time=await read_time(session),
        services=services,
        settings={
            "Часовой пояс ввода": f"UTC+{settings.local_utc_offset_hours} (Москва)",
            "Вход действует, часов": str(settings.auth_token_hours),
            "cuOpt: базовый лимит поиска, с": str(settings.cuopt_time_limit_seconds),
            "cuOpt: максимальный лимит, с": str(settings.cuopt_max_time_limit_seconds),
            "cuOpt: вес пробега в цели": str(settings.cuopt_distance_weight),
            "R5: таймаут запроса, с": str(settings.r5_timeout_seconds),
            "R5: расписания (GTFS)": str(settings.r5_gtfs_path),
            "Скорость пешком, км/ч": str(settings.walking_speed_kmh),
        },
        data=data,
    )
