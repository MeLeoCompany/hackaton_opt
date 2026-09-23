"""Журнал расчёта: что пишется в базу и как двигается прогресс (db/init/038)."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.errors import CalculationCancelled
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

    async def flush(self):
        pass

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
    async with (
        run_log.track("build", office_id=1, solver="cuopt"),
        run_log.step("Считаю матрицы", 10, 50),
    ):
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
    async with run_log.track("build", office_id=1), run_log.step("Считаю матрицы", 10, 50):
        assert run_log._current.get().percent == 10
        await run_log.note("блок 2 из 4", fraction=0.5)
        assert run_log._current.get().percent == 30
        await run_log.note("блок 4 из 4", fraction=1)
        assert run_log._current.get().percent == 50


@pytest.mark.asyncio
async def test_failed_run_keeps_the_reason(journal):
    with pytest.raises(ValueError, match="R5 недоступен"):
        async with run_log.track("replan", office_id=1):
            async with run_log.step("Считаю матрицы", 10, 50):
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
    async with run_log.track("build", office_id=1), run_log.step("Считаю матрицы", 10, 50):
        await run_log.note("блок 1 из 4", fraction=0.25)


@pytest.mark.asyncio
async def test_steps_outside_a_run_are_ignored(journal):
    """Расчёт из теста или фоновой задачи журнала не ведёт — и не падает."""
    async with run_log.step("Считаю матрицы", 10, 50):
        await run_log.note("блок 1 из 4", fraction=0.5)

    assert journal.added == []


@pytest.mark.asyncio
async def test_cancel_stops_the_run_between_steps(journal, monkeypatch):
    """Оператор нажал «Прервать»: расчёт останавливается на ближайшем шаге."""
    # первый шаг успевает пройти, кнопку нажимают во время него
    monkeypatch.setattr(run_log, "CANCEL_POLL_SECONDS", 0)  # без задержки между проверками
    monkeypatch.setattr(run_log, "_cancel_requested", AsyncMock(side_effect=[False, True, True]))
    steps = []

    with pytest.raises(CalculationCancelled, match="прерван оператором"):
        async with run_log.track("build", office_id=1):
            async with run_log.step("Считаю матрицы", 10, 50):
                steps.append("матрицы")
            async with run_log.step("Решаю задачу", 50, 80):
                steps.append("решатель")

    assert steps == ["матрицы"]  # до решателя дело не дошло
    assert values_of(journal.executed[-1])["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_does_not_wait_for_cuopt(journal, monkeypatch):
    """cuOpt на видеокарте не остановить: при отмене просто перестаём ждать результат."""
    monkeypatch.setattr(run_log, "_cancel_requested", AsyncMock(return_value=True))

    async def forever():
        await asyncio.sleep(30)
        return "поздно"

    async with run_log.track("build", office_id=1):
        solving = asyncio.create_task(forever())
        with pytest.raises(CalculationCancelled):
            await run_log.wait_cancellable(solving, poll_seconds=0.01)
        solving.cancel()


@pytest.mark.asyncio
async def test_waiting_returns_the_result_while_nobody_cancels(journal, monkeypatch):
    monkeypatch.setattr(run_log, "_cancel_requested", AsyncMock(return_value=False))

    async def quick():
        return "маршруты"

    async with run_log.track("build", office_id=1):
        assert await run_log.wait_cancellable(asyncio.create_task(quick()), 0.01) == "маршруты"


@pytest.mark.asyncio
async def test_service_logs_land_inside_the_step(journal):
    """Строки cuOpt и служб попадают в журнал тем же шагом, с уровнем и источником."""
    async with run_log.track("build", office_id=1), run_log.step("Решаю задачу", 45, 80):
        logging.getLogger("src.services.planner.cuopt_solver").info("cuOpt solved orders=3")
        logging.getLogger("src.services.travel.r5_provider").warning("R5 ответил медленно")
        await asyncio.sleep(0.05)  # перехват пишет их из своей задачи

    captured = {
        event.message: (event.level, event.source)
        for event in journal.added
        if isinstance(event, PlanRunEvent)
    }
    assert captured["cuOpt solved orders=3"] == ("info", "cuopt")
    assert captured["R5 ответил медленно"] == ("warning", "r5")


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "1 заявка"), (2, "2 заявки"), (5, "5 заявок"), (11, "11 заявок"), (21, "21 заявка")],
)
def test_plural_reads_like_russian(count, expected):
    assert run_log.plural(count, "заявка", "заявки", "заявок") == expected
