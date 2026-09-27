"""Пароль администратора приходит из окружения, а не из миграции."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.security import hash_password, verify_password
from src.services.users import admin_account


def admin(password="старый"):
    return SimpleNamespace(login="admin", password_hash=hash_password(password))


@pytest.mark.asyncio
async def test_password_is_taken_from_the_environment():
    user = admin()
    session = SimpleNamespace(commit=AsyncMock())

    with (
        patch.object(
            admin_account.users_repository, "find_user_by_login", AsyncMock(return_value=user)
        ),
        patch.object(admin_account.settings, "admin_password", "из-окружения"),
    ):
        changed = await admin_account.ensure_admin_password(session)

    assert changed is True
    assert verify_password("из-окружения", user.password_hash)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_matching_password_is_left_alone():
    """Пароль уже такой, какой просили: базу не трогаем на каждом старте."""
    user = admin("из-окружения")
    before = user.password_hash
    session = SimpleNamespace(commit=AsyncMock())

    with (
        patch.object(
            admin_account.users_repository, "find_user_by_login", AsyncMock(return_value=user)
        ),
        patch.object(admin_account.settings, "admin_password", "из-окружения"),
    ):
        changed = await admin_account.ensure_admin_password(session)

    assert changed is False
    assert user.password_hash == before
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_admin_is_not_created():
    """Учётки нет — значит её удалили осознанно: заводить заново не наше дело."""
    session = SimpleNamespace(commit=AsyncMock())

    with patch.object(
        admin_account.users_repository, "find_user_by_login", AsyncMock(return_value=None)
    ):
        assert await admin_account.ensure_admin_password(session) is False
