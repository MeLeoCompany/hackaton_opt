"""Очистка данных перед показом: что она стирает и как защищена от случайного нажатия."""

import pytest

from src.core.errors import DataError
from src.repositories.system import system_repository
from src.services.system import system_service


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["", "удали", "УДАЛИТ", "delete"])
async def test_wrong_word_deletes_nothing(word):
    """Без точного слова подтверждения до базы дело не доходит."""
    touched = False

    async def fail_if_called(_session):
        nonlocal touched
        touched = True
        return {}

    original = system_repository.wipe_operational_data
    system_repository.wipe_operational_data = fail_if_called
    try:
        with pytest.raises(DataError, match="УДАЛИТЬ"):
            await system_service.wipe_data(None, confirm=word)
    finally:
        system_repository.wipe_operational_data = original

    assert touched is False


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["УДАЛИТЬ", "удалить", "  Удалить  "])
async def test_confirmation_is_case_and_space_tolerant(word, monkeypatch):
    """Слово вводит человек: регистр и случайные пробелы значения не имеют."""

    async def wipe(_session):
        return {"Заявки": 2, "Планы": 1}

    committed = False

    class Session:
        async def commit(self):
            nonlocal committed
            committed = True

    monkeypatch.setattr(system_repository, "wipe_operational_data", wipe)

    done = await system_service.wipe_data(Session(), confirm=word, user_id=1)

    assert done.total == 3
    assert done.deleted == {"Заявки": 2, "Планы": 1}
    assert committed is True


def test_reference_tables_are_never_touched():
    """Справочники и учётки остаются: иначе после очистки нечем работать и некому входить."""
    kept = {"office", "brigade", "equipment", "skill", "transport", "priority", "work_type"}
    kept |= {"app_user", "request_status", "request_status_transition", "solver_settings"}

    assert kept.isdisjoint(system_repository.OPERATIONAL_TABLES)
