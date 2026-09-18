"""Учётки: заводит и правит администратор."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.security import hash_password
from src.models import AppUser, UserRole
from src.repositories.offices import offices_repository
from src.repositories.users import users_repository
from src.schemas.users import UserRead, UserWrite


class UserNotFoundError(NotFoundError):
    """Учётки с таким номером нет."""


class UserDataError(DataError):
    """Данные учётки не прошли проверку."""


class UserInUseError(InUseError):
    """Действие оставило бы систему без администратора."""


def to_user_read(user: AppUser) -> UserRead:
    return UserRead(
        id=user.id,
        login=user.login,
        name=user.name,
        role=user.role,
        office_id=user.office_id,
        is_active=user.is_active,
    )


async def list_users(session: AsyncSession) -> list[UserRead]:
    return [to_user_read(user) for user in await users_repository.list_users(session)]


async def create_user(session: AsyncSession, payload: UserWrite) -> UserRead:
    if not payload.password:
        raise UserDataError(["задайте пароль новой учётке"])
    await check_user(session, payload)
    user = users_repository.add_user(session, user_fields(payload))
    await session.flush()
    await session.commit()
    return to_user_read(user)


async def update_user(
    session: AsyncSession, user_id: int, payload: UserWrite, current: AppUser
) -> UserRead:
    user = await find_user(session, user_id)
    await check_user(session, payload, except_id=user_id)
    stays_admin = payload.role == UserRole.ADMIN.value and payload.is_active
    if user.role == UserRole.ADMIN.value and user.is_active and not stays_admin:
        await check_other_admin_remains(session)
    if user.id == current.id and not payload.is_active:
        raise UserInUseError("Нельзя выключить собственную учётку")
    users_repository.apply_changes(user, user_fields(payload))
    await session.commit()
    return to_user_read(user)


async def delete_user(session: AsyncSession, user_id: int, current: AppUser) -> None:
    user = await find_user(session, user_id)
    if user.id == current.id:
        raise UserInUseError("Нельзя удалить собственную учётку")
    if user.role == UserRole.ADMIN.value and user.is_active:
        await check_other_admin_remains(session)
    await users_repository.delete_user(session, user)
    await session.commit()


def user_fields(payload: UserWrite) -> dict:
    """Поля для БД: пароль — только хэшем и только если его задали."""
    fields = payload.model_dump(exclude={"password"})
    # администратор не привязан к офису: он выбирает офис сам
    if payload.role == UserRole.ADMIN.value:
        fields["office_id"] = None
    if payload.password:
        fields["password_hash"] = hash_password(payload.password)
    return fields


async def find_user(session: AsyncSession, user_id: int) -> AppUser:
    user = await users_repository.get_user(session, user_id)
    if user is None:
        raise UserNotFoundError(f"Учётка №{user_id} не найдена")
    return user


async def check_user(session: AsyncSession, payload: UserWrite, except_id: int | None = None) -> None:
    problems = []
    same_login = await users_repository.find_user_by_login(session, payload.login)
    if same_login is not None and same_login.id != except_id:
        problems.append(f"логин «{payload.login}» уже занят")
    if (
        payload.office_id is not None
        and payload.role == UserRole.DISPATCHER.value
        and await offices_repository.get_office(session, payload.office_id) is None
    ):
        problems.append(f"офиса №{payload.office_id} нет в справочнике")
    if problems:
        raise UserDataError(problems)


async def check_other_admin_remains(session: AsyncSession) -> None:
    """Последнего включённого администратора нельзя разжаловать, выключить или удалить."""
    if await users_repository.count_active_admins(session) <= 1:
        raise UserInUseError("Это последний администратор: без него некому управлять учётками")
