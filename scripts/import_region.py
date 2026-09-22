"""Загрузка экспериментального дня выбранного района в отдельный офис."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.audit_anonymized import (
    REGIONS,
    REQUIRED_CONTROL,
    REQUIRED_SYNTHETIC,
    audit_pair,
    read_source,
    source_file,
)
from scripts.geocode_regions import SLUGS
from scripts.import_east import WORK_TYPES, load_coordinates

ROOT = Path(__file__).resolve().parents[1]
DAY = datetime(2026, 8, 17, tzinfo=ZoneInfo("Europe/Moscow"))


def prepare(region: str, data_dir: Path, cache_path: Path, review_path: Path):
    _, problems = audit_pair(data_dir, region)
    if problems:
        raise ValueError("Ошибка исходных файлов: " + "; ".join(problems))
    requests, _ = read_source(
        source_file(data_dir, region, "Синтетические данные"), REQUIRED_SYNTHETIC
    )
    control, _ = read_source(
        source_file(data_dir, region, "Контрольное распределение"), REQUIRED_CONTROL
    )
    brigades = sorted({row["Бригада"] for _, row in control if row["Бригада"]})
    if not brigades:
        raise ValueError("В контрольном распределении нет списка бригад")
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


async def apply(dsn: str, region: str, rows: list[dict], brigades: list[str]) -> dict:
    import asyncpg

    office_name = f"{region} — эксперимент 17.08.2026"
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"{SLUGS[region]}-2026-08-17-import",
            )
            existing = await connection.fetchval(
                "SELECT id FROM office WHERE name = $1", office_name
            )
            if existing is not None:
                raise ValueError(
                    f"Экспериментальный офис уже существует (id={existing}); импорт отменён"
                )
            office = await connection.fetchrow(
                "SELECT address, latitude, longitude FROM office WHERE name = $1", region
            )
            if office is None:
                raise ValueError(f"Не найден исходный офис «{region}»")
            office_id = await connection.fetchval(
                "INSERT INTO office (name,address,latitude,longitude) VALUES ($1,$2,$3,$4) RETURNING id",
                office_name,
                office["address"],
                office["latitude"],
                office["longitude"],
            )
            shift_start, shift_end = DAY.replace(hour=9), DAY.replace(hour=23)
            for name in brigades:
                brigade_id = await connection.fetchval(
                    "INSERT INTO brigade (office_id,name) VALUES ($1,$2) RETURNING id",
                    office_id,
                    name,
                )
                engineer_id = await connection.fetchval(
                    """INSERT INTO engineer
                    (name,start_latitude,start_longitude,shift_start,shift_end,
                     transport_id,office_id,brigade_id,start_at_office)
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
                    "INSERT INTO engineer_skill (engineer_id,skill_id) VALUES ($1,$2)",
                    [(engineer_id, skill) for skill in (1, 2, 3)],
                )
            mapping = {}
            for row in rows:
                request_id = await connection.fetchval(
                    """INSERT INTO request
                    (latitude,longitude,address,duration_minutes,window_start,
                     window_end,priority_id,skill_id,transport_id,work_type_id,
                     office_id,status_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,4,$9,$10,1) RETURNING id""",
                    row["latitude"], row["longitude"], row["address"], row["duration"],
                    row["start"], row["end"], row["priority"], row["skill"],
                    row["work_type"], office_id,
                )
                mapping[row["source_id"]] = request_id
            return {
                "office_id": office_id,
                "requests": len(rows),
                "brigades": len(brigades),
                "source_to_db": mapping,
            }
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("region", choices=REGIONS)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "Обезличивание")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    directory = ROOT / "experiments" / SLUGS[args.region]
    rows, brigades = prepare(
        args.region, args.data_dir, directory / "geocodes.json", directory / "review.csv"
    )
    print(
        f"Проверено: {len(rows)} заявок, {len(brigades)} бригад; "
        f"типы: {dict(Counter(row['work_type'] for row in rows))}"
    )
    print("Допущения: общественный транспорт; навыки 1–3; смена 09:00–23:00")
    if args.apply:
        dsn = os.getenv(
            "EXPERIMENT_DATABASE_DSN", "postgresql://routing:routing@localhost:5432/routing"
        )
        result = asyncio.run(apply(dsn, args.region, rows, brigades))
        report = directory / "import_report.json"
        report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Загружен офис {result['office_id']}; отчёт: {report}")


if __name__ == "__main__":
    main()
