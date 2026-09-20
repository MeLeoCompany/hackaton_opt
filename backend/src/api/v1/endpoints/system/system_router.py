"""Системное время и параметры системы.

Часы видят все вошедшие — время показано в каждой вкладке. Перематывать и смотреть параметры
может только администратор: это инструмент демонстрации и наладки.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_user, require_admin
from src.db.session import get_db
from src.models import AppUser
from src.schemas.system import SystemInfo, SystemTimeRead, SystemTimeWrite
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
