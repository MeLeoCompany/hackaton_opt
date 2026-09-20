"""Журнал расчёта: что пишется в базу и как двигается прогресс (db/init/038)."""

from types import SimpleNamespace

import pytest

from src.models import PlanRun, PlanRunEvent
from src.services.planner import run_log


class FakeSession:
    """Сессия-заглушка: запоминает, что журнал добавил и что обновил."""

    def __init__(self, added: list, executed: list):
        self.added = added
        self.executed = executed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def add(self, item):
        self.added.append(item)

    async def execute(self, statement):
        self.executed.append(statement)

    async def commit(self):
        pass


@pytest.fixture
def journal(monkeypatch):
    added: list = []
    executed: list = []
    monkeypatch.setattr(run_log, "async_session_maker", lambda: FakeSession(added, executed))
    return SimpleNamespace(added=added, executed=executed)


def values_of(statement) -> dict:
    """Значения UPDATE как обычный словарь: SQLAlchemy держит их привязанными параметрами."""
    return {
        column.name: getattr(value, "value", value) for column, value in statement._values.items()
    }


@pytest.mark.asyncio
async def test_run_writes_start_steps_and_finish(journal):
    async with run_log.track("build", office_id=1, solver="cuopt"):
        await run_log.step("Считаю матрицы", 10, 50)
        await run_log.note("блок 1 из 4", fraction=0.25)

    run = journal.added[0]
    assert isinstance(run, PlanRun)
    assert (run.office_id, run.kind, run.status) == (1, "build", "running")
    assert [event.message for event in journal.added if isinstance(event, PlanRunEvent)] == [
        "Считаю матрицы",
        "блок 1 из 4",
        "Расчёт готов",
    ]
    assert values_of(journal.executed[-1])["status"] == "done"


@pytest.mark.asyncio
async def test_note_moves_progress_inside_the_step(journal):
    async with run_log.track("build", office_id=1):
        await run_log.step("Считаю матрицы", 10, 50)
        assert run_log._current.get().percent == 10
        await run_log.note("блок 2 из 4", fraction=0.5)
        assert run_log._current.get().percent == 30
        await run_log.note("блок 4 из 4", fraction=1)
        assert run_log._current.get().percent == 50


@pytest.mark.asyncio
async def test_failed_run_keeps_the_reason(journal):
    with pytest.raises(ValueError, match="R5 недоступен"):
        async with run_log.track("replan", office_id=1):
            await run_log.step("Считаю матрицы", 10, 50)
            raise ValueError("R5 недоступен")

    finish = values_of(journal.executed[-1])
    assert finish["status"] == "failed"
    assert "R5 недоступен" in finish["error"]


@pytest.mark.asyncio
async def test_broken_journal_does_not_break_the_calculation(monkeypatch):
    """Журнал — вспомогательный: его сбой не должен ронять расчёт."""

    def broken():
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(run_log, "async_session_maker", broken)
    async with run_log.track("build", office_id=1):
        await run_log.step("Считаю матрицы", 10, 50)
        await run_log.note("блок 1 из 4", fraction=0.25)


@pytest.mark.asyncio
async def test_steps_outside_a_run_are_ignored(journal):
    """Расчёт из теста или фоновой задачи журнала не ведёт — и не падает."""
    await run_log.step("Считаю матрицы", 10, 50)
    await run_log.note("блок 1 из 4", fraction=0.5)

    assert journal.added == []
