"""Учётки и разделение по офисам: вход, выбор офиса, чужие данные недоступны."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.api import deps
from src.core.security import create_token, hash_password, read_token, verify_password
from src.schemas.users import UserWrite
from src.services.engineers import engineers_service
from src.services.planner import planning_service
from src.services.requests import requests_service
from src.services.users import users_service

ADMIN = SimpleNamespace(id=1, role="admin", office_id=None, is_active=True)
DISPATCHER = SimpleNamespace(id=2, role="dispatcher", office_id=3, is_active=True)


def test_password_is_checked_by_hash():
    stored = hash_password("s3cret")

    assert "s3cret" not in stored
    assert verify_password("s3cret", stored)
    assert not verify_password("secret", stored)


@pytest.mark.parametrize(
    "stored",
    [
        "broken",
        "scrypt$not-a-number$8$1$salt$digest",
        "scrypt$16384$8$1$%%%$%%%",
    ],
)
def test_broken_password_hash_is_rejected_instead_of_crashing(stored):
    assert not verify_password("secret", stored)


def test_token_carries_user_and_rejects_tampering_and_expiry():
    token = create_token(7, now=1_000)

    assert read_token(token, now=1_001) == 7
    assert read_token(token[:-2] + "xx", now=1_001) is None
    assert read_token(token, now=1_000 + 13 * 3600) is None  # 12 часов по умолчанию


def test_token_clock_accepts_unix_epoch_as_explicit_time():
    token = create_token(7, now=0)

    assert read_token(token, now=1) == 7


@pytest.mark.asyncio
async def test_dispatcher_works_only_in_own_office_whatever_the_header_says():
    office = await deps.current_office_id(user=DISPATCHER, x_office_id=1, session=object())

    assert office == 3


@pytest.mark.asyncio
async def test_admin_works_in_chosen_office():
    with patch.object(
        deps.offices_repository, "get_office", AsyncMock(return_value=SimpleNamespace(id=2))
    ):
        office = await deps.current_office_id(user=ADMIN, x_office_id=2, session=object())

    assert office == 2


@pytest.mark.asyncio
async def test_admin_without_choice_gets_first_office():
    offices = [(SimpleNamespace(id=1), 0), (SimpleNamespace(id=2), 0)]
    with patch.object(deps.offices_repository, "list_offices", AsyncMock(return_value=offices)):
        office = await deps.current_office_id(user=ADMIN, x_office_id=None, session=object())

    assert office == 1


@pytest.mark.asyncio
async def test_dispatcher_cannot_use_admin_endpoints():
    with pytest.raises(HTTPException) as refused:
        await deps.require_admin(user=DISPATCHER)

    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_last_admin_cannot_be_deleted():
    other_admin = SimpleNamespace(id=5, role="admin", is_active=True)
    repository = users_service.users_repository
    with (
        patch.object(repository, "get_user", AsyncMock(return_value=other_admin)),
        patch.object(repository, "count_active_admins", AsyncMock(return_value=1)),
        pytest.raises(users_service.UserInUseError, match="последний администратор"),
    ):
        await users_service.delete_user(object(), 5, current=ADMIN)


def test_dispatcher_needs_an_office():
    with pytest.raises(ValidationError, match="диспетчеру нужен офис"):
        UserWrite(login="ivanov", name="Иванов", role="dispatcher", password="1234")


@pytest.mark.asyncio
async def test_request_of_another_office_looks_missing():
    foreign = SimpleNamespace(id=16, office_id=1)
    with (
        patch.object(
            requests_service.requests_repository, "get_request", AsyncMock(return_value=foreign)
        ),
        pytest.raises(requests_service.RequestNotFoundError),
    ):
        await requests_service.get_request(object(), 16, office_id=3)


@pytest.mark.asyncio
async def test_engineer_of_another_office_looks_missing():
    foreign = SimpleNamespace(id=4, office_id=1)
    with (
        patch.object(
            engineers_service.engineers_repository, "get_engineer", AsyncMock(return_value=foreign)
        ),
        pytest.raises(engineers_service.EngineerNotFoundError),
    ):
        await engineers_service.find_engineer(object(), 4, office_id=3)


@pytest.mark.asyncio
async def test_plan_of_another_office_cannot_be_approved():
    foreign = SimpleNamespace(id=9, office_id=1, approved_at=None)
    with (
        patch.object(
            planning_service.plans_repository, "get_plan", AsyncMock(return_value=foreign)
        ),
        pytest.raises(planning_service.PlanNotFoundError),
    ):
        await planning_service.approve_plan(object(), 9, office_id=3)


@pytest.mark.asyncio
async def test_import_cannot_overwrite_request_of_another_office():
    rows = [{"id": 16, "is_active": None}]
    repository = requests_service.requests_repository
    with (
        patch.object(repository, "lock_request_ids", AsyncMock()),
        patch.object(
            requests_service.references_repository, "list_equipment", AsyncMock(return_value=[])
        ),
        patch.object(requests_service, "load_reference_lookup", AsyncMock()),
        patch.object(
            requests_service,
            "parse_requests_csv",
            return_value=SimpleNamespace(rows=rows, errors=[]),
        ),
        patch.object(
            repository,
            "get_requests_by_ids",
            AsyncMock(return_value={16: SimpleNamespace(id=16, office_id=1)}),
        ),
        pytest.raises(requests_service.RequestDataError, match="другом офисе"),
    ):
        await requests_service.import_requests_csv(object(), b"csv", office_id=3)
