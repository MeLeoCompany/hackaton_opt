"""Системное время и параметры системы.

Часы видят все вошедшие — время показано в каждой вкладке. Перематывать и смотреть параметры
может только администратор: это инструмент демонстрации и наладки.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id, current_user, require_admin
from src.db.session import get_db
from src.models import AppUser
from src.schemas.system import (
    DemoModeWrite,
    PlanRunRead,
    SolverParams,
    SolverParamsRead,
    SystemInfo,
    SystemTimeRead,
    SystemTimeWrite,
)
from src.services.system import system_service

router = APIRouter()


@router.get("/time", response_model=SystemTimeRead, summary="Системное время сервера")
async def read_time(
    session: AsyncSession = Depends(get_db),
    _: AppUser = Depends(current_user),
) -> SystemTimeRead:
    return await system_service.read_time(session)


@router.put(
    "/time",
    response_model=SystemTimeRead,
    summary="Перемотать системное время (только администратор)",
    dependencies=[Depends(require_admin)],
)
async def set_time(
    payload: SystemTimeWrite,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(current_user),
) -> SystemTimeRead:
    """`now` — поставить часы на момент, `offset_seconds` — задать сдвиг; 0 — настоящее время."""
    return await system_service.set_time(session, payload, user.id)


@router.get(
    "/info",
    response_model=SystemInfo,
    summary="Параметры системы: версии, подключения, настройки (только администратор)",
    dependencies=[Depends(require_admin)],
)
async def read_info(session: AsyncSession = Depends(get_db)) -> SystemInfo:
    return await system_service.read_info(session)


@router.get(
    "/runs",
    response_model=list[PlanRunRead],
    summary="Журнал расчётов: что считали, сколько заняло и чем кончилось",
)
async def list_runs(
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    _: AppUser = Depends(current_user),
) -> list[PlanRunRead]:
    return await system_service.list_runs(session, office_id=office_id, limit=limit)


@router.get(
    "/runs/{run_id}",
    response_model=PlanRunRead,
    summary="Ход одного расчёта по шагам: по нему рисуется прогресс",
)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    _: AppUser = Depends(current_user),
) -> PlanRunRead:
    return await system_service.get_run(session, run_id, office_id=office_id)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=PlanRunRead,
    summary="Прервать идущий расчёт",
)
async def cancel_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
) -> PlanRunRead:
    """Расчёт останавливается на ближайшем шаге: ничего не сохраняется."""
    return await system_service.cancel_run(
        session, run_id, office_id=office_id, user_id=user.id
    )


@router.get(
    "/solver",
    response_model=SolverParamsRead,
    summary="Параметры расчёта по умолчанию",
)
async def read_solver_params(
    session: AsyncSession = Depends(get_db),
    _: AppUser = Depends(current_user),
) -> SolverParamsRead:
    """Их подставляет диалог расчёта; поменять на один расчёт можно прямо в нём."""
    return await system_service.read_solver_params(session)


@router.put(
    "/solver",
    response_model=SolverParamsRead,
    summary="Изменить параметры расчёта по умолчанию (только администратор)",
    dependencies=[Depends(require_admin)],
)
async def save_solver_params(
    payload: SolverParams,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(current_user),
) -> SolverParamsRead:
    return await system_service.save_solver_params(session, payload, user_id=user.id)


@router.put(
    "/demo",
    response_model=SystemTimeRead,
    summary="Включить или выключить режим демонстрации (только администратор)",
    dependencies=[Depends(require_admin)],
)
async def set_demo_mode(
    payload: DemoModeWrite,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(current_user),
) -> SystemTimeRead:
    """В режиме можно переводить время и синхронизировать маршруты с планом; выключили —
    часы возвращаются к настоящему времени."""
    return await system_service.set_demo_mode(session, payload.enabled, user_id=user.id)
