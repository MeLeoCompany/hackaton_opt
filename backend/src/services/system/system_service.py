"""Системное время и параметры системы.

Время сервера можно перемотать вперёд для демонстрации: тогда пересчёт плана «с текущего
момента», отметки бригад и расчёт опозданий считают «сейчас» сдвинутым. Сдвиг хранится
в базе (034) и держится в памяти процесса (`core/clock.py`).
"""

import platform
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.config import settings
from src.core.errors import DataError, NotFoundError
from src.models import AppUser, Brigade, Engineer, Office, Plan, Request
from src.repositories.plan_runs import plan_runs_repository
from src.repositories.system import system_repository
from src.schemas.system import (
    PlanRunEventRead,
    PlanRunRead,
    ServiceStatus,
    SolverParams,
    SolverParamsRead,
    SystemInfo,
    SystemTimeRead,
    SystemTimeWrite,
)

APP_VERSION = "0.1.0"
# перемотка — инструмент демонстрации: часы ставят в день, на котором лежат данные, поэтому
# назад можно так же далеко, как вперёд — на год
MIN_OFFSET_SECONDS = -366 * 24 * 3600
MAX_OFFSET_SECONDS = 366 * 24 * 3600


class SystemTimeError(DataError):
    """Сдвиг времени вне разумных границ или режим демонстрации выключен."""


class DemoModeRequired(DataError):
    """Отладочное действие без режима демонстрации."""


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
        demo_mode=row.demo_mode,
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
        raise SystemTimeError(["перематывать можно не больше чем на год назад или вперёд"])

    row = await system_repository.get_system_time(session)
    # вернуть настоящее время можно всегда, а переводить — только в режиме демонстрации
    if seconds and not row.demo_mode:
        raise SystemTimeError(
            ["переводить время можно только в режиме демонстрации — включите его в «Системе»"]
        )
    row.offset_seconds = seconds
    row.updated_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.commit()
    clock.set_offset(timedelta(seconds=seconds))
    return await read_time(session)


async def set_demo_mode(
    session: AsyncSession, enabled: bool, user_id: int | None = None
) -> SystemTimeRead:
    """Включает или выключает режим демонстрации.

    Выключили — часы возвращаются к настоящему времени: переводить их без режима уже нельзя,
    и система застряла бы в перемотанном дне.
    """
    row = await system_repository.get_system_time(session)
    row.demo_mode = enabled
    row.demo_mode_changed_at = datetime.now(UTC)
    row.demo_mode_changed_by = user_id
    if not enabled and row.offset_seconds:
        row.offset_seconds = 0
        row.updated_at = datetime.now(UTC)
        row.updated_by = user_id
    await session.commit()
    clock.set_offset(timedelta(seconds=row.offset_seconds))
    return await read_time(session)


async def require_demo_mode(session: AsyncSession) -> None:
    """Отладочные действия — только в режиме демонстрации, иначе ими можно испортить данные."""
    row = await system_repository.get_system_time(session)
    if not row.demo_mode:
        raise DemoModeRequired(
            ["синхронизировать маршруты с планом можно только в режиме демонстрации"]
        )


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
            "R5: таймаут запроса, с": str(settings.r5_timeout_seconds),
            "R5: расписания (GTFS)": str(settings.r5_gtfs_path),
            "Скорость пешком, км/ч": str(settings.walking_speed_kmh),
        },
        data=data,
    )


async def list_runs(session: AsyncSession, *, office_id: int, limit: int = 50) -> list[PlanRunRead]:
    """Журнал расчётов офиса: чем считали, сколько заняло и чем кончилось."""
    rows = await plan_runs_repository.list_runs(session, office_id=office_id, limit=limit)
    return [run_summary(run, user_name) for run, user_name in rows]


async def active_run(session: AsyncSession, *, office_id: int) -> PlanRunRead | None:
    """Идёт ли сейчас расчёт офиса: страница планов по нему возвращает полосу хода.

    Расчёт живёт на сервере, а не в браузере: оператор может уйти на другую страницу или
    перезагрузить её, и, вернувшись, должен снова видеть, что план считается.
    """
    run = await plan_runs_repository.active_run(session, office_id=office_id)
    return run_summary(run, None) if run is not None else None


async def get_run(session: AsyncSession, run_id: UUID, *, office_id: int) -> PlanRunRead:
    """Один запуск со всеми его шагами: по нему рисуется прогресс и разбирается зависание."""
    row = await plan_runs_repository.get_run(session, run_id, office_id=office_id)
    if row is None:
        raise NotFoundError(f"Расчёт {run_id} не найден")
    run, user_name = row
    summary = run_summary(run, user_name)
    events = await plan_runs_repository.list_events(session, run_id)
    summary.events = [PlanRunEventRead.model_validate(event) for event in events]
    return summary


def run_summary(run, user_name: str | None) -> PlanRunRead:
    finished = run.finished_at or clock.now()
    return PlanRunRead(
        id=run.id,
        plan_date=run.plan_date,
        kind=run.kind,
        solver=run.solver,
        status=run.status,
        step=run.step,
        progress=run.progress,
        plan_id=run.plan_id,
        error=run.error,
        cancel_requested=run.cancel_requested,
        user_name=user_name,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=max((finished - run.started_at).total_seconds(), 0.0),
    )


async def cancel_run(session: AsyncSession, run_id: UUID, *, office_id: int, user_id: int | None):
    """Оператор нажал «Прервать»: расчёт увидит флаг и остановится на ближайшем шаге.

    cuOpt на видеокарте остановить снаружи нельзя, поэтому расчёт перестаёт его ждать —
    оператор сразу получает управление, а поток досчитает вхолостую.
    """
    row = await plan_runs_repository.get_run(session, run_id, office_id=office_id)
    if row is None:
        raise NotFoundError(f"Расчёт {run_id} не найден")
    run, user_name = row
    if run.status == "running":
        await plan_runs_repository.request_cancel(session, run_id, user_id=user_id)
        await session.commit()
        await session.refresh(run)
    return run_summary(run, user_name)


async def read_solver_params(session: AsyncSession) -> SolverParamsRead:
    """Системные параметры расчёта: они подставляются в диалог расчёта по умолчанию."""
    row = await system_repository.get_solver_settings(session)
    author = await session.get(AppUser, row.updated_by) if row.updated_by else None
    return SolverParamsRead(
        time_limit_seconds=float(row.time_limit_seconds),
        seconds_per_location=float(row.seconds_per_location),
        max_time_limit_seconds=float(row.max_time_limit_seconds),
        free_locations=row.free_locations,
        distance_weight=float(row.distance_weight),
        transit_attempts=row.transit_attempts,
        verbose_log=row.verbose_log,
        updated_at=row.updated_at,
        updated_by=author.name if author else None,
    )


async def save_solver_params(
    session: AsyncSession, payload: SolverParams, *, user_id: int | None
) -> SolverParamsRead:
    """Новые параметры по умолчанию: следующие расчёты пойдут с ними."""
    row = await system_repository.get_solver_settings(session)
    row.time_limit_seconds = Decimal(str(payload.time_limit_seconds))
    row.seconds_per_location = Decimal(str(payload.seconds_per_location))
    row.max_time_limit_seconds = Decimal(str(payload.max_time_limit_seconds))
    row.free_locations = payload.free_locations
    row.distance_weight = Decimal(str(payload.distance_weight))
    row.transit_attempts = payload.transit_attempts
    row.verbose_log = payload.verbose_log
    row.updated_at = clock.now()
    row.updated_by = user_id
    await session.commit()
    return await read_solver_params(session)
