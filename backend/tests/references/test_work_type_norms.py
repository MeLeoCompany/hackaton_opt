"""Правка нормативов типа работ администратором."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.schemas.references import WorkTypeNormsWrite, WorkTypePriorityWrite
from src.services.references import references_service


def test_work_on_site_cannot_be_zero():
    with pytest.raises(ValidationError):
        WorkTypeNormsWrite(travel_minutes=20, work_minutes=0)
    with pytest.raises(ValidationError):
        WorkTypeNormsWrite(travel_minutes=-5, work_minutes=30)
    # дорога может быть нулевой: ТКД рядом с офисом
    WorkTypeNormsWrite(travel_minutes=0, work_minutes=30)


@pytest.mark.asyncio
async def test_norms_are_saved_and_baseline_reloaded():
    work_type = SimpleNamespace(
        id=4,
        name="Локальная заявка",
        skill_id=1,
        travel_minutes=20,
        work_minutes=30,
        baseline_minutes=50,
        priority_id=1,
    )

    async def refresh(item):
        # в БД baseline_minutes — вычисляемая колонка: дорога + работа
        item.baseline_minutes = item.travel_minutes + item.work_minutes

    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(side_effect=refresh))
    with patch.object(
        references_service.references_repository, "get_work_type", AsyncMock(return_value=work_type)
    ):
        saved = await references_service.update_work_type_norms(
            session, 4, WorkTypeNormsWrite(travel_minutes=15, work_minutes=45)
        )

    assert (saved.travel_minutes, saved.work_minutes, saved.baseline_minutes) == (15, 45, 60)
    # навык и название правкой нормативов не меняются
    assert (saved.name, saved.skill_id) == ("Локальная заявка", 1)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_work_type_is_not_found():
    with (
        patch.object(
            references_service.references_repository, "get_work_type", AsyncMock(return_value=None)
        ),
        pytest.raises(references_service.WorkTypeNotFoundError),
    ):
        await references_service.update_work_type_norms(
            SimpleNamespace(), 99, WorkTypeNormsWrite(travel_minutes=10, work_minutes=10)
        )


@pytest.mark.asyncio
async def test_default_priority_of_work_type_can_be_changed():
    work_type = SimpleNamespace(
        id=2,
        name="Авария на ТКД",
        skill_id=3,
        travel_minutes=20,
        work_minutes=60,
        baseline_minutes=80,
        priority_id=1,
    )
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    repository = references_service.references_repository
    with (
        patch.object(repository, "get_work_type", AsyncMock(return_value=work_type)),
        patch.object(
            repository,
            "list_priorities",
            AsyncMock(return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)]),
        ),
    ):
        saved = await references_service.update_work_type_priority(
            session, 2, WorkTypePriorityWrite(priority_id=2)
        )
        assert saved.priority_id == 2

        with pytest.raises(references_service.WorkTypeDataError, match="нет в справочнике"):
            await references_service.update_work_type_priority(
                session, 2, WorkTypePriorityWrite(priority_id=9)
            )
