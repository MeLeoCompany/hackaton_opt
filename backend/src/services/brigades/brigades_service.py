"""Справочник бригад: бригада работает в регионе своего офиса.

Бригада — постоянный состав; её смена на день — исполнитель (строка engineer): при добавлении
исполнителя на день выбирают бригаду. Здесь же бригаде задают логин и пароль для мобильного
приложения — как пользователям. Технически это учётка app_user с ролью brigade, привязанная к
бригаде; её имя всегда равно названию бригады.

Справочник доступен администратору (любой офис — выбранный в интерфейсе) и диспетчеру (свой
офис): офис приходит из current_office_id.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.security import hash_password
from src.models import AppUser, Brigade, UserRole
from src.repositories.brigades import brigades_repository
from src.repositories.users import users_repository
from src.schemas.brigades import BrigadeRead, BrigadeWrite


class BrigadeNotFoundError(NotFoundError):
    """Бригады с таким номером в офисе нет."""


class BrigadeDataError(DataError):
    """Данные бригады не прошли проверку."""


class BrigadeInUseError(InUseError):
    """Бригаду нельзя удалить: у неё есть смены."""


def to_brigade_read(brigade: Brigade, account: AppUser | None, shift_count: int) -> BrigadeRead:
    return BrigadeRead(
        id=brigade.id,
        office_id=brigade.office_id,
        name=brigade.name,
        is_active=brigade.is_active,
        login=account.login if account else None,
        shift_count=shift_count,
    )


async def list_brigades(session: AsyncSession, office_id: int) -> list[BrigadeRead]:
    return [
        to_brigade_read(brigade, account, count)
        for brigade, account, count in await brigades_repository.list_brigades(session, office_id)
    ]


async def find_brigade(session: AsyncSession, brigade_id: int, office_id: int) -> Brigade:
    """Бригада офиса. Чужая выглядит как несуществующая."""
    brigade = await brigades_repository.get_brigade(session, brigade_id)
    if brigade is None or brigade.office_id != office_id:
        raise BrigadeNotFoundError(f"Бригада №{brigade_id} не найдена")
    return brigade


async def create_brigade(
    session: AsyncSession, payload: BrigadeWrite, office_id: int
) -> BrigadeRead:
    await check_brigade(session, payload, office_id)
    if payload.login and not payload.password:
        raise BrigadeDataError(["задайте пароль для входа бригады в приложение"])
    brigade = brigades_repository.add_brigade(
        session, {"office_id": office_id, "name": payload.name, "is_active": payload.is_active}
    )
    await session.flush()
    account = sync_account(session, brigade, None, payload)
    await session.commit()
    return to_brigade_read(brigade, account, 0)


async def update_brigade(
    session: AsyncSession, brigade_id: int, payload: BrigadeWrite, office_id: int
) -> BrigadeRead:
    brigade = await find_brigade(session, brigade_id, office_id)
    account = await brigades_repository.get_account(session, brigade.id)
    await check_brigade(session, payload, office_id, brigade=brigade, account=account)
    if payload.login and account is None and not payload.password:
        raise BrigadeDataError(["задайте пароль для входа бригады в приложение"])

    if payload.name != brigade.name:
        await brigades_repository.rename_shifts(session, brigade.id, payload.name)
    brigade.name = payload.name
    brigade.is_active = payload.is_active

    if payload.login is None and account is not None:
        # логин стёрли — входа в приложение у бригады больше нет
        await users_repository.delete_user(session, account)
        account = None
    else:
        account = sync_account(session, brigade, account, payload)
    await session.commit()
    return to_brigade_read(
        brigade, account, await brigades_repository.count_shifts(session, brigade.id)
    )


async def delete_brigade(session: AsyncSession, brigade_id: int, office_id: int) -> None:
    brigade = await find_brigade(session, brigade_id, office_id)
    shifts = await brigades_repository.count_shifts(session, brigade.id)
    if shifts:
        raise BrigadeInUseError(
            f"У бригады «{brigade.name}» есть смены ({shifts}) — её нельзя удалить, "
            "выключите её: новые смены ей заводить не будут, в приложение она не войдёт"
        )
    account = await brigades_repository.get_account(session, brigade.id)
    if account is not None:
        await users_repository.delete_user(session, account)
    await brigades_repository.delete_brigade(session, brigade)
    await session.commit()


async def check_brigade(
    session: AsyncSession,
    payload: BrigadeWrite,
    office_id: int,
    *,
    brigade: Brigade | None = None,
    account: AppUser | None = None,
) -> None:
    problems = []
    same_name = await brigades_repository.find_by_name(session, office_id, payload.name)
    if same_name is not None and (brigade is None or same_name.id != brigade.id):
        problems.append(f"бригада «{payload.name}» в офисе уже есть")
    if payload.login:
        same_login = await users_repository.find_user_by_login(session, payload.login)
        if same_login is not None and (account is None or same_login.id != account.id):
            problems.append(f"логин «{payload.login}» уже занят")
    if problems:
        raise BrigadeDataError(problems)


def sync_account(
    session: AsyncSession, brigade: Brigade, account: AppUser | None, payload: BrigadeWrite
) -> AppUser | None:
    """Учётка бригады для приложения: имя — название бригады, включена вместе с бригадой."""
    if not payload.login:
        return account
    fields = {
        "login": payload.login,
        "name": brigade.name,
        "role": UserRole.BRIGADE.value,
        "office_id": brigade.office_id,
        "brigade_id": brigade.id,
        "is_active": brigade.is_active,
    }
    if payload.password:
        fields["password_hash"] = hash_password(payload.password)
    if account is None:
        return users_repository.add_user(session, fields)
    users_repository.apply_changes(account, fields)
    return account
