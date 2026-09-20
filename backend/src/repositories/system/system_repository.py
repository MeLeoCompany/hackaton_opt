"""Чтение и запись сдвига системного времени. Коммит делает сервис."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SystemTime


async def get_system_time(session: AsyncSession) -> SystemTime:
    """Строка сдвига; её заводит миграция 034, но на всякий случай создаём при отсутствии."""
    row = await session.get(SystemTime, 1)
    if row is None:
        row = SystemTime(id=1, offset_seconds=0)
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
