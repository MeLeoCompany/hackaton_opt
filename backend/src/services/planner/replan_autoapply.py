"""Пересчёт вступает в силу сам — в тот момент, на который посчитан (docs/algoV2.md, шаг 6).

А если к этому моменту он уже не годится, не ждём его: фоновая проверка помечает такой
пересчёт недействительным сразу, как день изменился.

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


async def void_stale() -> list[int]:
    """Помечает недействительными пересчёты, которые уже не вступят в силу.

    Таких два вида: прежний пересчёт плана, который посчитали заново, и пересчёт, чей день
    успел измениться — появилась или отменилась заявка. Ждать их момента незачем: утверждение
    их не примет, а пока они висят, бригадам закрыт выезд туда, куда они их не ведут
    (departure_gate). Лучше сказать сразу — оператор посчитает заново (docs/algoV2.md, шаги 6 и 8).
    """
    voided = []
    async with async_session_maker() as session:
        waiting = await plans_repository.waiting_replans(session)
        # на один план ждёт только последний расчёт: иначе в свой момент их вступило бы
        # в силу несколько подряд и бригады получили бы то один маршрут, то другой
        newest: dict[int, int] = {}
        for plan in waiting:
            newest[plan.parent_plan_id] = max(newest.get(plan.parent_plan_id, 0), plan.id)
        for plan in waiting:
            last = newest[plan.parent_plan_id]
            if plan.id != last:
                reason = f"Отменён пересчётом №{last}: план пересчитали заново"
            else:
                reason = await planning_service.replan_stale_reason(session, plan)
            if reason is None:
                continue
            plan.voided_at = clock.now()
            plan.void_reason = reason
            voided.append(plan.id)
            logger.info("пересчёт №%s уже не вступит в силу: %s", plan.id, reason)
        if voided:
            await session.commit()
    return voided


async def apply_due() -> list[int]:
    """Вводит в силу все пересчёты, чей момент настал. Возвращает номера вступивших в силу."""
    applied = []
    async with async_session_maker() as session:
        for plan in await plans_repository.due_replans(session, clock.now()):
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
            # сначала отзываем те, что уже не вступят в силу, потом вводим подошедшие
            await void_stale()
            await apply_due()
        except Exception:
            logger.warning("Пересчёты: не удалось проверить, повторю позже", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)
