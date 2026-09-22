"""Память решений cuOpt: одинаковая задача — одинаковый ответ (docs/algoCachV1.md).

cuOpt ограничен только временем поиска и ищет на видеокарте параллельно, поэтому на один и
тот же вход каждый раз находит немного другое решение того же качества. Замер на наших днях:
5 разных решений из 5 и при 3, и при 30 секундах — больший лимит воспроизводимости не даёт.

Поэтому решение запоминается по отпечатку всего, что уходит в cuOpt: матрицы, окна, награды,
бригады, веса цели и лимит времени. Такой же вход — берём то же решение без поиска: план
воспроизводится до визита, а вслед за ним и проверка расписания, и плечи в кеше R5.
Изменился хоть один параметр — ищем заново.
"""

import hashlib
import logging
from importlib import metadata

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.core.config import settings
from src.db.session import async_session_maker
from src.models import SolverMemory

logger = logging.getLogger(__name__)

# меняется постановка задачи для cuOpt (run_cuopt) — поднимаем версию, старые ответы не берутся
MODEL_VERSION = 1


def _cuopt_version() -> str:
    for package in ("cuopt-cu13", "cuopt-cu12", "cuopt"):
        try:
            return metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"


def fingerprint(inputs) -> str:
    """Отпечаток входа cuOpt (SolverInputs): всё, от чего зависит ответ решателя."""
    digest = hashlib.sha256()

    def add(value) -> None:
        if isinstance(value, np.ndarray):
            digest.update(str(value.dtype).encode())
            digest.update(repr(value.shape).encode())
            digest.update(np.ascontiguousarray(value).tobytes())
        else:
            digest.update(repr(value).encode())
        digest.update(b"|")

    add(("model", MODEL_VERSION, _cuopt_version()))
    add(inputs.location_count)
    for transport_id in sorted(inputs.cost_matrices):
        add(transport_id)
        add(inputs.cost_matrices[transport_id])
    for transport_id in sorted(inputs.travel_time_matrices):
        add(transport_id)
        add(inputs.travel_time_matrices[transport_id])
    for array in (
        inputs.vehicle_locations,
        inputs.vehicle_types,
        inputs.vehicle_shift_start,
        inputs.vehicle_shift_end,
        inputs.vehicle_fixed_costs,
        inputs.order_locations,
        inputs.order_window_start,
        inputs.order_window_end,
        inputs.order_service_minutes,
        inputs.order_prizes,
    ):
        add(array)
    for allowed in inputs.order_allowed_vehicles:
        add(np.asarray(allowed))
    add(inputs.objective.distance_weight)
    add(inputs.time_limit_seconds)
    return digest.hexdigest()


def _plain(record: dict) -> dict:
    """Строка маршрута cuOpt с типами numpy -> обычные числа для JSON (без потери точности)."""
    return {
        key: (value.item() if isinstance(value, np.generic) else value)
        for key, value in record.items()
    }


async def recall(input_hash: str) -> list[dict] | None:
    """Решение этой же задачи, если её уже решали; нет или база не ответила — None."""
    if not settings.travel_cache_enabled:
        return None
    try:
        async with async_session_maker() as session:
            return await session.scalar(
                select(SolverMemory.route_records).where(SolverMemory.input_hash == input_hash)
            )
    except Exception:
        logger.warning("Память решений недоступна — решаю заново", exc_info=True)
        return None


async def remember(input_hash: str, route_records: list[dict]) -> None:
    """Запомнить решение; не записали — в следующий раз просто решим заново."""
    if not settings.travel_cache_enabled:
        return
    try:
        async with async_session_maker() as session:
            statement = insert(SolverMemory).values(
                input_hash=input_hash, route_records=[_plain(record) for record in route_records]
            )
            await session.execute(statement.on_conflict_do_nothing(index_elements=["input_hash"]))
            await session.commit()
    except Exception:
        logger.warning("Память решений: не удалось сохранить решение", exc_info=True)
