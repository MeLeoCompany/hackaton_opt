"""HTTP-эндпоинты исполнителей.

Ошибки сервиса (не найден, неверные данные, используется в плане) превращаются
в ответы 404 / 422 / 409 обработчиками в src/main.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.engineers import EngineerCreate, EngineerRead, EngineerWrite
from src.services.engineers import engineers_service

router = APIRouter()


@router.get("", response_model=list[EngineerRead], summary="Все исполнители")
async def list_engineers(plan_date: date | None = None, session: AsyncSession = Depends(get_db)):
    return await engineers_service.list_engineers(session, plan_date)


@router.get("/{engineer_id}", response_model=EngineerRead, summary="Один исполнитель")
async def get_engineer(engineer_id: int, session: AsyncSession = Depends(get_db)):
    return await engineers_service.get_engineer(session, engineer_id)


@router.post("", response_model=EngineerRead, status_code=status.HTTP_201_CREATED, summary="Добавить исполнителя")
async def create_engineer(payload: EngineerCreate, session: AsyncSession = Depends(get_db)):
    return await engineers_service.create_engineer(session, payload)


@router.put("/{engineer_id}", response_model=EngineerRead, summary="Изменить исполнителя")
async def update_engineer(engineer_id: int, payload: EngineerWrite, session: AsyncSession = Depends(get_db)):
    return await engineers_service.update_engineer(session, engineer_id, payload)


@router.delete("/{engineer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить исполнителя")
async def delete_engineer(engineer_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    await engineers_service.delete_engineer(session, engineer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
