"""Справочник бригад офиса: администратору (выбранный офис) и диспетчеру (свой офис)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id
from src.db.session import get_db
from src.schemas.brigades import BrigadeRead, BrigadeWrite
from src.services.brigades import brigades_service

router = APIRouter()


@router.get("", response_model=list[BrigadeRead], summary="Бригады офиса")
async def list_brigades(
    session: AsyncSession = Depends(get_db), office_id: int = Depends(current_office_id)
):
    return await brigades_service.list_brigades(session, office_id)


@router.post(
    "", response_model=BrigadeRead, status_code=status.HTTP_201_CREATED, summary="Добавить бригаду"
)
async def create_brigade(
    payload: BrigadeWrite,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await brigades_service.create_brigade(session, payload, office_id)


@router.put("/{brigade_id}", response_model=BrigadeRead, summary="Изменить бригаду")
async def update_brigade(
    brigade_id: int,
    payload: BrigadeWrite,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await brigades_service.update_brigade(session, brigade_id, payload, office_id)


@router.delete("/{brigade_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить бригаду")
async def delete_brigade(
    brigade_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
) -> Response:
    await brigades_service.delete_brigade(session, brigade_id, office_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
