"""Журнал расчёта: дерево шагов, строки внешних служб и прерывание по кнопке.

Расчёт большого дня идёт минутами — матрицы Valhalla и R5, cuOpt, проверка расписания.
Журнал отвечает на три вопроса: что считается прямо сейчас, где расчёт стоял дольше всего
и почему он кончился так, а не иначе.

Устройство:
  - шаг (`step`) — узел дерева со временем начала, окончания и длительностью; подробности
    внутри шага (`note`) становятся его детьми, поэтому строка раскрывается в подробный ход;
  - строки логов cuOpt, R5 и Valhalla перехватываются и ложатся в тот же шаг, с уровнем
    (`warning`, `error`) и источником;
  - текущий запуск живёт в contextvar: шаги пишут и загрузчик, и провайдеры, и решатель,
    не прокидывая параметры через все слои. Запуска нет (тесты) — функции ничего не делают;
  - каждая запись идёт своей короткой транзакцией, иначе прогресс не виден снаружи, пока
    расчёт держит свою;
  - `check_cancelled` смотрит флаг «Прервать» и останавливает расчёт между шагами.
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, update

from src.core import clock
from src.core.errors import CalculationCancelled
from src.db.session import async_session_maker
from src.models import PlanRun, PlanRunEvent

logger = logging.getLogger(__name__)

# сколько строк пишем внутри одного шага: блоков матрицы бывают сотни, журнал ими не заваливаем
MAX_EVENTS_PER_STEP = 60
# как часто спрашиваем базу, не нажали ли «Прервать»
CANCEL_POLL_SECONDS = 0.5
# чьи логи забираем в журнал: наши службы и сам решатель
CAPTURED_LOGGERS = ("src.", "cuopt")
# по имени логгера понятно, чья это строка
LOG_SOURCES = {
    "src.services.planner.cuopt_solver": "cuopt",
    "cuopt": "cuopt",
    "src.services.travel.r5_provider": "r5",
    "src.services.travel.r5_access": "r5",
    "src.services.travel.valhalla_provider": "valhalla",
    "src.services.travel.travel_service": "travel",
}
LOG_LEVELS = {logging.WARNING: "warning", logging.ERROR: "error", logging.CRITICAL: "error"}


@dataclass
class RunState:
    """Текущий запуск: куда писать, в каком шаге идём и когда в последний раз спрашивали отмену."""

    run_id: uuid.UUID
    step: str = ""
    percent_from: int = 0
    percent_to: int = 0
    percent: int = 0
    # открытые шаги: последний — тот, к которому цепляются подробности
    stack: list[int] = field(default_factory=list)
    events_in_step: int = 0
    cancel_checked_at: float = 0.0


_current: ContextVar[RunState | None] = ContextVar("plan_run", default=None)


def plural(count: int, one: str, few: str, many: str) -> str:
    """«1 заявка», «3 заявки», «5 заявок» — журнал читают люди."""
    tail, hundred = count % 10, count % 100
    if tail == 1 and hundred != 11:
        return f"{count} {one}"
    if 2 <= tail <= 4 and not 12 <= hundred <= 14:
        return f"{count} {few}"
    return f"{count} {many}"


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
    """Запуск расчёта: начало, конец, ошибка и перехват логов внешних служб."""
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
    capture = _start_capture(state)
    try:
        yield state
    except CalculationCancelled as cancelled:
        await _finish(state, "cancelled", error=str(cancelled))
        raise
    except Exception as error:
        await _finish(state, "failed", error=f"{type(error).__name__}: {error}")
        raise
    else:
        await _finish(state, "done")
    finally:
        _stop_capture(capture)
        _current.reset(token)


@asynccontextmanager
async def step(title: str, percent_from: int, percent_to: int, *, source: str = "planner"):
    """Шаг расчёта: узел журнала, внутри которого лежат его подробности.

    Перед шагом проверяем, не нажали ли «Прервать»: между шагами расчёт останавливается
    без потерь — ничего не сохранено.
    """
    await check_cancelled()
    state = _current.get()
    if state is None:
        yield
        return
    state.step = title
    state.percent_from = percent_from
    state.percent_to = percent_to
    state.percent = percent_from
    state.events_in_step = 0
    await _save_progress(state)
    event_id = await _add_event(state, title, "info", source, node=True)
    if event_id is not None:
        state.stack.append(event_id)
    started = time.perf_counter()
    try:
        yield
    finally:
        if event_id is not None and state.stack and state.stack[-1] == event_id:
            state.stack.pop()
        await _close_event(event_id, round((time.perf_counter() - started) * 1000))


async def note(
    message: str,
    *,
    fraction: float | None = None,
    level: str = "info",
    source: str = "planner",
    details: dict | None = None,
) -> None:
    """Подробность текущего шага: «блок 3 из 12», «попытка 2», строка службы.

    fraction — доля шага (0..1): по ней двигается общий процент.
    """
    state = _current.get()
    if state is None:
        return
    if fraction is not None:
        span = state.percent_to - state.percent_from
        state.percent = min(state.percent_to, state.percent_from + round(span * fraction))
        await _save_progress(state)
    state.events_in_step += 1
    if state.events_in_step > MAX_EVENTS_PER_STEP and level == "info":
        return
    await _add_event(state, message, level, source, details=details)


async def check_cancelled() -> None:
    """Оператор нажал «Прервать» — останавливаем расчёт на ближайшем шаге."""
    state = _current.get()
    if state is None:
        return
    now = time.monotonic()
    if now - state.cancel_checked_at < CANCEL_POLL_SECONDS:
        return
    state.cancel_checked_at = now
    if await _cancel_requested(state.run_id):
        raise CalculationCancelled("Расчёт прерван оператором")


async def wait_cancellable(task: asyncio.Task, poll_seconds: float = CANCEL_POLL_SECONDS):
    """Ждёт задачу, не переставая спрашивать про «Прервать».

    cuOpt считает на видеокарте в своём потоке, и остановить его снаружи нельзя. Поэтому
    при отмене мы просто перестаём ждать результат: оператор сразу получает управление,
    а поток досчитает и его результат никому не достанется.
    """
    while True:
        done, _ = await asyncio.wait({task}, timeout=poll_seconds)
        if done:
            return task.result()
        state = _current.get()
        if state is None:
            continue
        if await _cancel_requested(state.run_id):
            # результат больше не нужен, но исключение забрать надо — иначе шум в логах
            task.add_done_callback(lambda finished: finished.exception())
            raise CalculationCancelled("Расчёт прерван оператором")


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


# ---- запись в базу: короткими транзакциями, чтобы прогресс был виден снаружи ----


async def _cancel_requested(run_id: uuid.UUID) -> bool:
    asked: list[bool] = []

    async def ask(session):
        result = await session.execute(
            select(PlanRun.cancel_requested).where(PlanRun.id == run_id)
        )
        asked.append(bool(result.scalar_one_or_none()))

    await _write(ask)
    return bool(asked and asked[0])


async def _finish(state: RunState, status: str, error: str | None = None) -> None:
    if status == "done":
        state.step = "Готово"
        state.percent = 100
    message = {
        "done": "Расчёт готов",
        "cancelled": "Расчёт прерван оператором",
    }.get(status, f"Расчёт прерван: {error}")
    level = "info" if status == "done" else ("warning" if status == "cancelled" else "error")
    await _add_event(state, message, level, "planner", root=True)
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
                cancelled_at=clock.now() if status == "cancelled" else None,
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


async def _add_event(
    state: RunState,
    message: str,
    level: str,
    source: str,
    *,
    node: bool = False,
    root: bool = False,
    details: dict | None = None,
) -> int | None:
    """Пишет строку журнала и возвращает её номер — по нему шаг потом закрывается."""
    # шаг верхнего уровня цепляем к корню, подробности — к открытому шагу
    parent_id = None if root or node else (state.stack[-1] if state.stack else None)
    event = PlanRunEvent(
        run_id=state.run_id,
        at=clock.now(),
        level=level,
        step=state.step,
        message=message,
        progress=state.percent,
        parent_id=parent_id,
        source=source,
        details=details,
    )

    async def add(session):
        session.add(event)
        await session.flush()

    await _write(add)
    return event.id


async def _close_event(event_id: int | None, duration_ms: int) -> None:
    if event_id is None:
        return
    await _write(
        lambda session: session.execute(
            update(PlanRunEvent)
            .where(PlanRunEvent.id == event_id)
            .values(finished_at=clock.now(), duration_ms=duration_ms)
        )
    )


async def _write(action) -> None:
    """Каждая запись — своя короткая транзакция; сбой журнала не должен ронять расчёт."""
    try:
        async with async_session_maker() as session:
            result = action(session)
            if result is not None and hasattr(result, "__await__"):
                await result
            await session.commit()
    except Exception as error:  # noqa: BLE001 — журнал не должен ломать расчёт
        logger.warning("Журнал расчёта не записан: %s", error)


# ---- перехват логов: строки cuOpt, R5 и Valhalla ложатся в тот же шаг ----


class _QueueHandler(logging.Handler):
    """Складывает строки логов в очередь: писать в базу из чужого потока нельзя."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        super().__init__(level=logging.INFO)
        self.loop = loop
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith(CAPTURED_LOGGERS) or record.name == __name__:
            return
        item = (
            record.getMessage(),
            LOG_LEVELS.get(record.levelno, "info"),
            LOG_SOURCES.get(record.name, record.name.split(".")[-1]),
        )
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
        except RuntimeError:
            pass  # цикл уже закрыт — расчёт всё равно закончился


def _start_capture(state: RunState):
    """Включает перехват на время расчёта: cuOpt логирует из своего потока.

    Логгерам служб поднимаем уровень до INFO: по умолчанию он наследуется от root (WARNING),
    и строки вроде «cuOpt solved …» просто не доходили бы до журнала.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    queue: asyncio.Queue = asyncio.Queue()
    handler = _QueueHandler(loop, queue)
    targets = [logging.getLogger(name.rstrip(".")) for name in CAPTURED_LOGGERS]
    levels = [(target, target.level) for target in targets]
    for target in targets:
        target.addHandler(handler)
        if target.level == logging.NOTSET or target.level > logging.INFO:
            target.setLevel(logging.INFO)

    async def drain():
        while True:
            message, level, source = await queue.get()
            token = _current.set(state)
            try:
                await note(message, level=level, source=source)
            finally:
                _current.reset(token)

    return handler, asyncio.create_task(drain()), levels


def _stop_capture(capture) -> None:
    if capture is None:
        return
    handler, task, levels = capture
    for target, level in levels:
        target.removeHandler(handler)
        target.setLevel(level)
    task.cancel()
