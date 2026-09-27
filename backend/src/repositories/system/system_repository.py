"""Чтение и запись сдвига системного времени. Коммит делает сервис."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SolverSettings, SystemTime


async def get_system_time(session: AsyncSession) -> SystemTime:
    """Строка сдвига; её заводит миграция 034, но на всякий случай создаём при отсутствии."""
    row = await session.get(SystemTime, 1)
    if row is None:
        row = SystemTime(id=1, offset_seconds=0)
        session.add(row)
        await session.flush()
    return row


async def get_solver_settings(session: AsyncSession) -> SolverSettings:
    """Строка параметров расчёта; её заводит миграция 040, но подстрахуемся."""
    row = await session.get(SolverSettings, 1)
    if row is None:
        row = SolverSettings(id=1)
        session.add(row)
        await session.flush()
    return row


async def counts(session: AsyncSession, models: dict[str, type]) -> dict[str, int]:
    """Сколько записей в каждой таблице — для страницы параметров системы."""
    result = {}
    for name, model in models.items():
        rows = await session.execute(select(model.id))
        result[name] = len(rows.scalars().all())
    return result


# Рабочие данные: всё, что накапливается за день работы и что перед показом хочется убрать.
# Порядок не важен — таблицы чистятся одной командой, но список должен быть полным: если
# забыть таблицу, которая ссылается на очищаемую, Postgres откажется её трогать
OPERATIONAL_TABLES: dict[str, str] = {
    "assignment": "Назначения",
    "plan_route": "Маршруты планов",
    "plan_run_event": "События расчётов",
    "plan_run": "Запуски расчётов",
    "event": "Отметки бригад",
    "request_equipment": "Оборудование заявок",
    "request_fact": "Факты по заявкам",
    "request_status_history": "История статусов",
    "request": "Заявки",
    "engineer_equipment": "Оборудование смен",
    "engineer_skill": "Навыки смен",
    "engineer": "Смены",
    "plan": "Планы",
}


async def wipe_operational_data(session: AsyncSession) -> dict[str, int]:
    """Удалить рабочие данные, оставив справочники и учётки. Коммит делает сервис.

    TRUNCATE, а не DELETE: он не строит план по каждой строке и заодно возвращает счётчики
    id к единице — после очистки заявки и планы снова нумеруются с первого.
    """
    deleted: dict[str, int] = {}
    for table, title in OPERATIONAL_TABLES.items():
        rows = await session.execute(text(f"SELECT count(*) FROM {table}"))
        count = rows.scalar_one()
        if count:
            deleted[title] = count
    tables = ", ".join(OPERATIONAL_TABLES)
    await session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY"))
    return deleted
