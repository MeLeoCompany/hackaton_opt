"""Пересчёт вступает в силу сам — в тот момент, на который посчитан (docs/algoV2.md, шаг 6).

Расчёт идёт на точку «сейчас плюс запас» (settings.replan_lead_minutes): эти минуты бригады
едут по действующему плану, оператор успевает обзвонить клиентов и посмотреть маршруты. Когда
момент настаёт, пересчёт заменяет прежний план сам — оператору не нужно успевать нажать кнопку.

Если к этому моменту появились новые вводные — заявка, отмена, выбившаяся бригада, выезд не
туда, — пересчёт в силу не вступает: он помечается недействительным с причиной, у плана
загорается «!», бригады продолжают ехать по прежнему плану, а оператор считает заново с новыми
вводными. Сами мы расчёт не перезапускаем: на меняющемся дне это крутилось бы без конца.
"""

import asyncio
import logging

from src.core import clock
from src.core.errors import DataError, InUseError
from src.db.session import async_session_maker
from src.repositories.plans import plans_repository
from src.services.planner import planning_service

logger = logging.getLogger(__name__)

# как часто смотрим, не пора ли какому-нибудь пересчёту вступать в силу
TICK_SECONDS = 10


async def apply_due() -> list[int]:
    """Вводит в силу все пересчёты, чей момент настал. Возвращает номера вступивших в силу."""
    applied = []
    async with async_session_maker() as session:
        while due := await plans_repository.due_replans(session, clock.now()):
            plan = due[0]
            try:
                await planning_service.approve_replan(session, plan)
                applied.append(plan.id)
                logger.info("пересчёт №%s вступил в силу", plan.id)
            except (InUseError, DataError) as error:
                await session.rollback()
                plan.voided_at = clock.now()
                plan.void_reason = str(error)
                await session.commit()
                logger.info("пересчёт №%s не вступил в силу: %s", plan.id, error)
    return applied


async def loop() -> None:
    """Фоновая проверка: ошибки не роняют приложение, следующий круг попробует снова."""
    while True:
        try:
            await apply_due()
        except Exception:
            logger.warning("Пересчёты: не удалось проверить, повторю позже", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)
