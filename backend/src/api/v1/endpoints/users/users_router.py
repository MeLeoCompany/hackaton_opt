"""Учётки — только для администратора."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.db.session import get_db
from src.models import AppUser
from src.schemas.users import UserRead, UserWrite
from src.services.users import users_service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserRead], summary="Все учётки")
async def list_users(session: AsyncSession = Depends(get_db)):
    return await users_service.list_users(session)


@router.post(
    "", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Добавить учётку"
)
async def create_user(payload: UserWrite, session: AsyncSession = Depends(get_db)):
    return await users_service.create_user(session, payload)


@router.put("/{user_id}", response_model=UserRead, summary="Изменить учётку")
async def update_user(
    user_id: int,
    payload: UserWrite,
    session: AsyncSession = Depends(get_db),
    admin: AppUser = Depends(require_admin),
):
    return await users_service.update_user(session, user_id, payload, admin)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить учётку")
async def delete_user(
    user_id: int, session: AsyncSession = Depends(get_db), admin: AppUser = Depends(require_admin)
) -> Response:
    await users_service.delete_user(session, user_id, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
