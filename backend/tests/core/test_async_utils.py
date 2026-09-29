import asyncio

import pytest

from src.core.async_utils import gather_strict


@pytest.mark.asyncio
async def test_gather_strict_cancels_remaining_operations_after_failure():
    cancelled = asyncio.Event()

    async def fail() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("ошибка R5")

    async def wait_forever() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(RuntimeError, match="ошибка R5"):
        await gather_strict([fail(), wait_forever()])

    assert cancelled.is_set()
