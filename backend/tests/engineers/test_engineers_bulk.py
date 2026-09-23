"""Групповая правка и удаление смен: галочки в таблице, одно действие на все отмеченные.

Правка идёт целиком или никак: если после переноса бригада окажется в двух сменах сразу,
не меняется ничего. Удаление — что можно, с перечнем причин по остальным.
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.local_day import local_timezone
from src.schemas.engineers import EngineerBulkUpdate
from src.services.engineers import engineers_service

MSK = local_timezone()


def stored(engineer_id, brigade_id=None, hour=9, skills=(1,)):
    return SimpleNamespace(
        id=engineer_id,
        office_id=1,
        brigade_id=brigade_id or engineer_id,
        name=f"Бригада {engineer_id}",
        transport_id=1,
        shift_start=datetime(2026, 8, 17, hour, tzinfo=MSK),
        shift_end=datetime(2026, 8, 17, hour + 8, tzinfo=MSK),
        start_at_office=False,
        start_latitude=55.7,
        start_longitude=37.6,
        skills=[SimpleNamespace(id=skill_id) for skill_id in skills],
    )


async def bulk_update(engineers, payload, *, brigade_shifts=()):
    session = SimpleNamespace(commit=AsyncMock())
    found = {engineer.id: engineer for engineer in engineers}
    with (
        patch.object(
            engineers_service,
            "find_engineer",
            AsyncMock(side_effect=lambda _, engineer_id, __: found[engineer_id]),
        ),
        patch.object(
            engineers_service.references_repository,
            "list_transports",
            AsyncMock(return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)]),
        ),
        patch.object(
            engineers_service.engineers_repository,
            "get_skills_by_ids",
            AsyncMock(
                side_effect=lambda _, ids: [SimpleNamespace(id=skill_id) for skill_id in ids]
            ),
        ),
        patch.object(
            engineers_service.engineers_repository,
            "list_brigade_shifts",
            AsyncMock(return_value=list(brigade_shifts)),
        ),
    ):
        return await engineers_service.update_engineers(session, payload, office_id=1)


@pytest.mark.asyncio
async def test_only_marked_fields_change():
    engineers = [stored(1), stored(2, hour=12)]

    report = await bulk_update(engineers, EngineerBulkUpdate(engineer_ids=[1, 2], transport_id=2))

    assert report.updated == 2
    assert [engineer.transport_id for engineer in engineers] == [2, 2]
    # смены у каждой остались своими
    assert [engineer.shift_start.astimezone(MSK).hour for engineer in engineers] == [9, 12]


@pytest.mark.asyncio
async def test_day_transfer_keeps_the_time():
    engineers = [stored(1, hour=9)]

    await bulk_update(
        engineers, EngineerBulkUpdate(engineer_ids=[1], move_to_day=date(2026, 8, 20))
    )

    start = engineers[0].shift_start.astimezone(MSK)
    end = engineers[0].shift_end.astimezone(MSK)
    assert (start.date(), start.hour) == (date(2026, 8, 20), 9)
    assert (end.date(), end.hour) == (date(2026, 8, 20), 17)


@pytest.mark.asyncio
async def test_skills_replace_the_previous_ones():
    engineers = [stored(1, skills=(1, 2))]

    await bulk_update(engineers, EngineerBulkUpdate(engineer_ids=[1], skill_ids=[3]))

    assert [skill.id for skill in engineers[0].skills] == [3]


@pytest.mark.asyncio
async def test_two_shifts_of_one_brigade_are_refused():
    """После переноса обе смены одной бригады встали бы на один день и час."""
    engineers = [stored(1, brigade_id=7, hour=9), stored(2, brigade_id=7, hour=10)]

    with pytest.raises(engineers_service.EngineerDataError, match="две смены сразу"):
        await bulk_update(
            engineers, EngineerBulkUpdate(engineer_ids=[1, 2], move_to_day=date(2026, 8, 20))
        )

    assert engineers[0].shift_start.astimezone(MSK).date() == date(2026, 8, 17)


@pytest.mark.asyncio
async def test_unknown_skill_is_refused():
    engineers = [stored(1)]
    session = SimpleNamespace(commit=AsyncMock())
    with (
        patch.object(engineers_service, "find_engineer", AsyncMock(return_value=engineers[0])),
        patch.object(
            engineers_service.engineers_repository,
            "get_skills_by_ids",
            AsyncMock(return_value=[]),
        ),
        pytest.raises(engineers_service.EngineerDataError, match="навыков №9 нет"),
    ):
        await engineers_service.update_engineers(
            session, EngineerBulkUpdate(engineer_ids=[1], skill_ids=[9]), office_id=1
        )


@pytest.mark.asyncio
async def test_delete_removes_what_it_can_and_explains_the_rest():
    async def delete_one(session, engineer_id, office_id):
        if engineer_id == 2:
            raise engineers_service.EngineerInUseError(
                f"Исполнителя №{engineer_id} нельзя удалить: он есть в планах"
            )

    with patch.object(engineers_service, "delete_engineer", AsyncMock(side_effect=delete_one)):
        report = await engineers_service.delete_engineers(object(), [1, 2, 3], office_id=1)

    assert report.deleted == 2
    assert [problem.id for problem in report.problems] == [2]
    assert "есть в планах" in report.problems[0].reason
