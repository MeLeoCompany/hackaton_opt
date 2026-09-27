"""Пароль администратора берётся из окружения, а не из миграции.

В миграции лежит только сама учётка `admin` со значением, под которое не подходит ни один
пароль: хранить рабочий пароль в репозитории нельзя. Настоящий пароль приходит переменной
ADMIN_PASSWORD (локально — backend/.env, на сервере — deploy/deploy.env) и ставится при
старте приложения. Поменяли переменную и перезапустили — пароль обновился.

Пароль, заданный вручную в интерфейсе, не затирается: если он уже совпадает с ADMIN_PASSWORD
или переменную не трогали, приложение ничего не делает.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import hash_password, verify_password
from src.repositories.users import users_repository

logger = logging.getLogger(__name__)

ADMIN_LOGIN = "admin"
DEFAULT_PASSWORD = "admin"


async def ensure_admin_password(session: AsyncSession) -> bool:
    """Ставит администратору пароль из окружения. True — пароль пришлось обновить."""
    # про заводской пароль предупреждаем на каждом старте, а не только когда ставим его:
    # система с общеизвестным паролем не должна выглядеть нормально работающей
    if settings.admin_password == DEFAULT_PASSWORD:
        logger.warning(
            "ADMIN_PASSWORD не задан — у администратора пароль «%s». Задайте его в окружении "
            "или смените в интерфейсе: иначе войти может кто угодно",
            DEFAULT_PASSWORD,
        )
    admin = await users_repository.find_user_by_login(session, ADMIN_LOGIN)
    if admin is None:
        return False
    if verify_password(settings.admin_password, admin.password_hash):
        return False
    admin.password_hash = hash_password(settings.admin_password)
    await session.commit()
    logger.info("Пароль администратора взят из окружения")
    return True
