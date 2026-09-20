"""Журнал расчёта: что система считает прямо сейчас и сколько это заняло.

Расчёт большого дня идёт минутами — матрицы Valhalla и R5, cuOpt, проверка расписания.
Без журнала интерфейс выглядит зависшим, поэтому каждый шаг пишется в базу отдельной
транзакцией: прогресс видно снаружи, пока расчёт ещё идёт.

Текущий запуск живёт в contextvar, поэтому шаги пишутся прямо из загрузчика, провайдеров
и решателя — без прокидывания параметров через все слои. Запуска нет (тесты, фоновые
вызовы) — все функции ничего не делают.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import update

from src.core import clock
from src.db.session import async_session_maker
from src.models import PlanRun, PlanRunEvent

logger = logging.getLogger(__name__)


@dataclass
class RunState:
    """Текущий запуск: куда писать и в каком диапазоне процентов идёт шаг."""

    run_id: uuid.UUID
    step: str = ""
    percent_from: int = 0
    percent_to: int = 0
    percent: int = 0
    events: int = field(default=0)


_current: ContextVar[RunState | None] = ContextVar("plan_run", default=None)

# сколько событий пишем на один шаг: блоков матрицы бывают сотни, журнал ими не заваливаем
MAX_EVENTS_PER_STEP = 40


def current_run_id() -> uuid.UUID | None:
    state = _current.get()
    return state.run_id if state else None


@asynccontextmanager
async def track(
    kind: str,
    *,
    office_id: int,
    plan_date: date | None = None,
    solver: str | None = None,
    user_id: int | None = None,
    run_id: uuid.UUID | None = None,
):
    """Запуск расчёта: пишет начало, конец и ошибку, если расчёт не получился."""
    state = RunState(run_id=run_id or uuid.uuid4())
    token = _current.set(state)
    await _write(
        lambda session: session.add(
            PlanRun(
                id=state.run_id,
                office_id=office_id,
                plan_date=plan_date,
                kind=kind,
                solver=solver,
                status="running",
                step="Готовлю расчёт",
                progress=0,
                user_id=user_id,
                started_at=clock.now(),
            )
        )
    )
    try:
        yield state
    except Exception as error:
        await _finish(state, "failed", error=f"{type(error).__name__}: {error}")
        raise
    else:
        await _finish(state, "done")
    finally:
        _current.reset(token)


async def step(title: str, percent_from: int, percent_to: int) -> None:
    """Новый шаг расчёта: его название видно в прогрессе, а доли — в событиях шага."""
    state = _current.get()
    if state is None:
        return
    state.step = title
    state.percent_from = percent_from
    state.percent_to = percent_to
    state.percent = percent_from
    state.events = 0
    await _save_progress(state)
    await _add_event(state, title, "info")


async def note(message: str, *, fraction: float | None = None, level: str = "info") -> None:
    """Подробность текущего шага: «блок 3 из 12», «попытка 2», сколько чего нашлось.

    fraction — доля шага (0..1): по ней двигается общий процент.
    """
    state = _current.get()
    if state is None:
        return
    if fraction is not None:
        span = state.percent_to - state.percent_from
        state.percent = min(state.percent_to, state.percent_from + round(span * fraction))
        await _save_progress(state)
    state.events += 1
    if state.events > MAX_EVENTS_PER_STEP and level == "info":
        return
    await _add_event(state, message, level)


async def attach_plan(plan_id: int) -> None:
    """Расчёт сохранён: по журналу видно, какой план из него получился."""
    state = _current.get()
    if state is None:
        return
    await _write(
        lambda session: session.execute(
            update(PlanRun).where(PlanRun.id == state.run_id).values(plan_id=plan_id)
        )
    )


async def _finish(state: RunState, status: str, error: str | None = None) -> None:
    if status == "done":
        state.step = "Готово"
        state.percent = 100
    await _add_event(
        state,
        "Расчёт готов" if status == "done" else f"Расчёт прерван: {error}",
        "info" if status == "done" else "error",
    )
    await _write(
        lambda session: session.execute(
            update(PlanRun)
            .where(PlanRun.id == state.run_id)
            .values(
                status=status,
                error=error,
                progress=100 if status == "done" else state.percent,
                step="" if status == "done" else state.step,
                finished_at=clock.now(),
            )
        )
    )


async def _save_progress(state: RunState) -> None:
    await _write(
        lambda session: session.execute(
            update(PlanRun)
            .where(PlanRun.id == state.run_id)
            .values(step=state.step, progress=state.percent)
        )
    )


async def _add_event(state: RunState, message: str, level: str) -> None:
    await _write(
        lambda session: session.add(
            PlanRunEvent(
                run_id=state.run_id,
                at=clock.now(),
                level=level,
                step=state.step,
                message=message,
                progress=state.percent,
            )
        )
    )


async def _write(action) -> None:
    """Каждая запись — своя короткая транзакция: иначе прогресс не виден, пока идёт расчёт.

    Журнал — вспомогательный: его сбой не должен ронять сам расчёт.
    """
    try:
        async with async_session_maker() as session:
            result = action(session)
            if result is not None and hasattr(result, "__await__"):
                await result
            await session.commit()
    except Exception as error:  # noqa: BLE001 — журнал не должен ломать расчёт
        logger.warning("Журнал расчёта не записан: %s", error)
