"""Кто делает запрос и в каком офисе — единая точка для всех эндпоинтов.

Сервисы получают номер офиса отсюда и не знают, откуда он взялся: у диспетчера это офис
учётки (выбрать другой он не может), у администратора — выбранный в интерфейсе офис из
заголовка X-Office-Id, а без заголовка — первый офис справочника.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models import AppUser, UserRole
from src.repositories.offices import offices_repository
from src.services.auth import auth_service
from src.services.auth.auth_service import AuthError


async def current_user(
    authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_db)
) -> AppUser:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    try:
        return await auth_service.user_from_token(session, token)
    except AuthError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(error), headers={"WWW-Authenticate": "Bearer"}
        ) from error


async def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это доступно только администратору")
    return user


async def current_office_id(
    user: AppUser = Depends(current_user),
    x_office_id: int | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> int:
    if user.role != UserRole.ADMIN.value:
        # диспетчер работает только в своём офисе, что бы ни прислал в заголовке
        return user.office_id
    if x_office_id is not None:
        if await offices_repository.get_office(session, x_office_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Офис №{x_office_id} не найден")
        return x_office_id
    offices = await offices_repository.list_offices(session)
    if not offices:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Заведите хотя бы один офис в справочнике"
        )
    return offices[0][0].id
