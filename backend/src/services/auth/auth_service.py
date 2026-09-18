"""Вход по логину и паролю и «кто сейчас вошёл»."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_token, read_token, verify_password
from src.models import AppUser
from src.repositories.offices import offices_repository
from src.repositories.users import users_repository
from src.schemas.auth import CurrentUser, LoginResponse


class AuthError(Exception):
    """Не вошёл, неверный пароль, токен истёк или учётка выключена -> 401."""


async def login(session: AsyncSession, login_name: str, password: str) -> LoginResponse:
    user = await users_repository.find_user_by_login(session, login_name)
    # одно сообщение на оба случая: не подсказываем, какие логины существуют
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Неверный логин или пароль")
    if not user.is_active:
        raise AuthError("Учётка выключена — обратитесь к администратору")
    return LoginResponse(token=create_token(user.id), user=await to_current_user(session, user))


async def user_from_token(session: AsyncSession, token: str | None) -> AppUser:
    user_id = read_token(token) if token else None
    if user_id is None:
        raise AuthError("Войдите в систему")
    user = await users_repository.get_user(session, user_id)
    if user is None or not user.is_active:
        raise AuthError("Учётка недоступна — войдите заново")
    return user


async def to_current_user(session: AsyncSession, user: AppUser) -> CurrentUser:
    office = (
        await offices_repository.get_office(session, user.office_id)
        if user.office_id is not None
        else None
    )
    return CurrentUser(
        id=user.id,
        login=user.login,
        name=user.name,
        role=user.role,
        office_id=user.office_id,
        office_name=office.name if office else None,
    )
