"""Небольшие примитивы конкурентного выполнения с явной отменой."""

import asyncio
from collections.abc import Awaitable, Sequence


async def gather_strict[T](awaitables: Sequence[Awaitable[T]]) -> list[T]:
    """Дождаться всех операций; при первой ошибке отменить и дождаться остальных.

    Обычный asyncio.gather пробрасывает первую ошибку, но уже запущенные запросы могут
    продолжить работу. Для тяжёлых вызовов R5 это оставляет незаметную нагрузку после
    отменённого расчёта.
    """
    tasks: list[asyncio.Future[T]] = [asyncio.ensure_future(value) for value in awaitables]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
