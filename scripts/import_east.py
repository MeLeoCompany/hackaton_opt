"""Загрузка экспериментального дня «Востока» в отдельный офис.

По умолчанию выполняется только проверка источников. Запись требует --apply.
Контрольное распределение используется для списка бригад, но не для назначений.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.audit_anonymized import (
    REQUIRED_CONTROL,
    REQUIRED_SYNTHETIC,
    audit_pair,
    read_source,
    source_file,
)

ROOT = Path(__file__).resolve().parents[1]
OFFICE_NAME = "Восток — эксперимент 17.08.2026"
DAY = datetime(2026, 8, 17, tzinfo=ZoneInfo("Europe/Moscow"))
WORK_TYPES = {
    "Подключение": (1, 2, 70),
    "Дозаказ": (3, 2, 20),
    "Локальная заявка": (4, 1, 30),
    "Глобальная проблема": (2, 3, 80),
}


def coordinate(value: str, *, latitude: bool) -> Decimal:
    try:
        result = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"Некорректная координата: {value!r}") from exc
    low, high = (
        (Decimal("54.2"), Decimal("56.9"))
        if latitude
        else (Decimal("35.1"), Decimal("40.3"))
    )
    if not result.is_finite() or not low <= result <= high:
        raise ValueError(f"Координата за пределами Московского региона: {value!r}")
    return result


def load_coordinates(
    cache_path: Path, review_path: Path
) -> dict[str, tuple[Decimal, Decimal]]:
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    resolved = {
        address: (
            coordinate(str(item["latitude"]), latitude=True),
            coordinate(str(item["longitude"]), latitude=False),
        )
        for address, item in cache.items()
        if item["status"] == "exact_house"
    }
    seen: set[str] = set()
    with review_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            address = row["адрес"]
            if address in seen:
                raise ValueError(f"Повторный адрес в review.csv: {address}")
            seen.add(address)
            if address in resolved:
                raise ValueError(
                    f"Лишняя ручная координата для подтверждённого дома: {address}"
                )
            if address not in cache:
                raise ValueError(f"Адрес из review.csv отсутствует в кеше: {address}")
            resolved[address] = (
                coordinate(row["широта_проверенная"], latitude=True),
                coordinate(row["долгота_проверенная"], latitude=False),
            )
    return resolved


def prepare(
    data_dir: Path, cache_path: Path, review_path: Path
) -> tuple[list[dict], list[str]]:
    _, problems = audit_pair(data_dir, "Восток")
    if problems:
        raise ValueError("Ошибка исходных файлов: " + "; ".join(problems))
    requests, _ = read_source(
        source_file(data_dir, "Восток", "Синтетические данные"), REQUIRED_SYNTHETIC
    )
    control, _ = read_source(
        source_file(data_dir, "Восток", "Контрольное распределение"), REQUIRED_CONTROL
    )
    brigades = sorted({row["Бригада"] for _, row in control if row["Бригада"]})
    if len(brigades) != 12:
        raise ValueError(f"Ожидалось 12 бригад, найдено {len(brigades)}")
    coords = load_coordinates(cache_path, review_path)
    source_addresses = {row["Адрес"] for _, row in requests}
    missing = source_addresses - coords.keys()
    extra = coords.keys() - source_addresses
    if missing or extra:
        raise ValueError(
            f"Адреса без координат: {sorted(missing)}; лишние: {sorted(extra)}"
        )
    prepared = []
    for line, row in requests:
        category = row["Тип заявки BK"]
        if category not in WORK_TYPES:
            raise ValueError(f"Неизвестный тип заявки в строке {line}: {category}")
        work_type, skill, duration = WORK_TYPES[category]
        start = datetime.strptime(row["Начало"], "%d.%m.%Y %H:%M").replace(
            tzinfo=DAY.tzinfo
        )
        end = datetime.strptime(row["Окончание"], "%d.%m.%Y %H:%M").replace(
            tzinfo=DAY.tzinfo
        )
        if start.date() != DAY.date() or end.date() != DAY.date() or end <= start:
            raise ValueError(f"Неверный день или окно в строке {line}")
        prepared.append(
            {
                "source_id": row["Заявка"],
                "address": row["Адрес"],
                "latitude": coords[row["Адрес"]][0],
                "longitude": coords[row["Адрес"]][1],
                "start": start,
                "end": end,
                "work_type": work_type,
                "skill": skill,
                "duration": duration,
                "priority": 2 if row["Тип заявки HD"] == "Авария" else 1,
            }
        )
    return prepared, brigades


async def apply(dsn: str, rows: list[dict], brigades: list[str]) -> dict:
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('east-2026-08-17-import'))"
            )
            existing = await connection.fetchval(
                "SELECT id FROM office WHERE name = $1", OFFICE_NAME
            )
            if existing is not None:
                raise ValueError(
                    f"Экспериментальный офис уже существует (id={existing}); импорт отменён"
                )
            office = await connection.fetchrow(
                "SELECT address, latitude, longitude FROM office WHERE name = 'Восток'"
            )
            if office is None:
                raise ValueError("Не найден исходный офис «Восток»")
            office_id = await connection.fetchval(
                "INSERT INTO office (name, address, latitude, longitude) VALUES ($1,$2,$3,$4) RETURNING id",
                OFFICE_NAME,
                office["address"],
                office["latitude"],
                office["longitude"],
            )
            shift_start = DAY.replace(hour=9)
            shift_end = DAY.replace(hour=23)
            for name in brigades:
                brigade_id = await connection.fetchval(
                    "INSERT INTO brigade (office_id, name) VALUES ($1,$2) RETURNING id",
                    office_id,
                    name,
                )
                engineer_id = await connection.fetchval(
                    """INSERT INTO engineer
                    (name, start_latitude, start_longitude, shift_start, shift_end,
                     transport_id, office_id, brigade_id, start_at_office)
                    VALUES ($1,$2,$3,$4,$5,4,$6,$7,TRUE) RETURNING id""",
                    name,
                    office["latitude"],
                    office["longitude"],
                    shift_start,
                    shift_end,
                    office_id,
                    brigade_id,
                )
                await connection.executemany(
                    "INSERT INTO engineer_skill (engineer_id, skill_id) VALUES ($1,$2)",
                    [(engineer_id, skill) for skill in (1, 2, 3)],
                )
            mapping = {}
            for row in rows:
                request_id = await connection.fetchval(
                    """INSERT INTO request
                    (latitude, longitude, address, duration_minutes, window_start,
                     window_end, priority_id, skill_id, transport_id, work_type_id,
                     office_id, status_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,4,$9,$10,1) RETURNING id""",
                    row["latitude"],
                    row["longitude"],
                    row["address"],
                    row["duration"],
                    row["start"],
                    row["end"],
                    row["priority"],
                    row["skill"],
                    row["work_type"],
                    office_id,
                )
                mapping[row["source_id"]] = request_id
            count = await connection.fetchval(
                "SELECT count(*) FROM request WHERE office_id = $1", office_id
            )
            if count != len(rows):
                raise RuntimeError("Число загруженных заявок не совпало с источником")
            return {
                "office_id": office_id,
                "requests": count,
                "brigades": len(brigades),
                "source_to_db": mapping,
            }
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "Обезличивание")
    parser.add_argument(
        "--cache", type=Path, default=ROOT / "experiments/east/geocodes.json"
    )
    parser.add_argument(
        "--review", type=Path, default=ROOT / "experiments/east/review.csv"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "experiments/east/import_report.json"
    )
    parser.add_argument(
        "--apply", action="store_true", help="создать офис, бригады и заявки"
    )
    args = parser.parse_args()
    rows, brigades = prepare(args.data_dir, args.cache, args.review)
    print(
        f"Проверено: {len(rows)} заявок, {len(brigades)} бригад; типы: {dict(Counter(row['work_type'] for row in rows))}"
    )
    print(
        "Допущения: общественный транспорт; навыки 1–3; смена 09:00–23:00; длительности из work_type"
    )
    if args.apply:
        dsn = os.getenv(
            "EAST_DATABASE_DSN", "postgresql://routing:routing@localhost:5432/routing"
        )
        result = asyncio.run(apply(dsn, rows, brigades))
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Загружен офис {result['office_id']}; отчёт: {args.report}")


if __name__ == "__main__":
    main()
