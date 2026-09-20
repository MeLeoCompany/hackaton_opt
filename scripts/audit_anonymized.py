"""Проверка исходных CSV перед подготовкой реального сценария планирования.

Только читает файлы. Контрольное распределение остаётся эталоном для сравнения,
а не источником назначений для решателя. Отчёт не содержит адресов и номеров заявок.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REGIONS = ("Восток", "Юго-восток", "Югоцентр")
COMMON_FIELDS = ("Тип заявки BK", "Тип заявки HD", "Начало", "Окончание", "Район")
REQUIRED_SYNTHETIC = ("Заявка", *COMMON_FIELDS, "Адрес")
REQUIRED_CONTROL = (*REQUIRED_SYNTHETIC, "Статус BK", "Бригада")
APARTMENT = re.compile(r",\s*кв\.?\s*.*$", re.IGNORECASE)
MOSCOW = ZoneInfo("Europe/Moscow")


def normalized_address(value: str) -> str:
    """Адрес контрольной записи может дополнительно содержать номер квартиры."""
    return "".join(APARTMENT.sub("", value).casefold().split())


def source_file(directory: Path, region: str, kind: str) -> Path:
    matches = sorted(directory.glob(f"{region} {kind}*.csv"))
    if len(matches) != 1:
        raise ValueError(
            f"{region}: ожидался один файл «{kind}», найдено {len(matches)}"
        )
    return matches[0]


def read_source(
    path: Path, required: tuple[str, ...]
) -> tuple[list[tuple[int, dict[str, str]]], str | None]:
    with path.open(encoding="cp1251", newline="") as source:
        reader = csv.DictReader(source, delimiter=";")
        missing = set(required) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{path.name}: отсутствуют колонки {', '.join(sorted(missing))}"
            )
        rows: list[tuple[int, dict[str, str]]] = []
        offices: list[str] = []
        for line, raw in enumerate(reader, start=2):
            if None in raw:
                raise ValueError(f"{path.name}:{line}: лишние поля в строке")
            row = {key: (value or "").strip() for key, value in raw.items()}
            identifier = row["Заявка"]
            if identifier.isdecimal():
                rows.append((line, row))
            elif identifier.casefold() == "адрес офиса":
                offices.append(row.get("Тип заявки BK", ""))
            elif any(row.values()):
                raise ValueError(f"{path.name}:{line}: неизвестная служебная строка")
    if len(offices) > 1:
        raise ValueError(f"{path.name}: несколько строк с адресом офиса")
    return rows, offices[0] if offices else None


def duplicate_lines(rows: list[tuple[int, dict[str, str]]]) -> list[list[int]]:
    by_id: dict[str, list[int]] = defaultdict(list)
    for line, row in rows:
        by_id[row["Заявка"]].append(line)
    return [lines for lines in by_id.values() if len(lines) > 1]


def check_windows(rows: list[tuple[int, dict[str, str]]]) -> list[int]:
    bad = []
    for line, row in rows:
        try:
            start = datetime.strptime(row["Начало"], "%d.%m.%Y %H:%M").replace(
                tzinfo=MOSCOW
            )
            end = datetime.strptime(row["Окончание"], "%d.%m.%Y %H:%M").replace(
                tzinfo=MOSCOW
            )
            if end <= start:
                bad.append(line)
        except ValueError:
            bad.append(line)
    return bad


def audit_pair(directory: Path, region: str) -> tuple[dict[str, object], list[str]]:
    synthetic_path = source_file(directory, region, "Синтетические данные")
    control_path = source_file(directory, region, "Контрольное распределение")
    synthetic, office = read_source(synthetic_path, REQUIRED_SYNTHETIC)
    control, _ = read_source(control_path, REQUIRED_CONTROL)
    problems = []
    if not office:
        problems.append("нет адреса офиса в синтетическом файле")
    if len(synthetic) != len(control):
        problems.append(f"число заявок различается: {len(synthetic)} и {len(control)}")
    mismatches = []
    for (synthetic_line, left), (control_line, right) in zip(
        synthetic, control, strict=False
    ):
        if any(
            left[field] != right[field] for field in COMMON_FIELDS
        ) or normalized_address(left["Адрес"]) != normalized_address(right["Адрес"]):
            mismatches.append([synthetic_line, control_line])
    if mismatches:
        problems.append(f"несовпадающие строки синтетика/контроль: {mismatches}")
    synthetic_bad_windows = check_windows(synthetic)
    control_bad_windows = check_windows(control)
    if synthetic_bad_windows or control_bad_windows:
        problems.append(
            f"неверные окна: синтетика {synthetic_bad_windows}, контроль {control_bad_windows}"
        )
    duplicate_synthetic = duplicate_lines(synthetic)
    if duplicate_synthetic:
        problems.append(
            f"повторяющиеся номера в синтетике: строки {duplicate_synthetic}"
        )

    status = Counter(row["Статус BK"] for _, row in control)
    brigades = {row["Бригада"] for _, row in control if row["Бригада"]}
    result: dict[str, object] = {
        "синтетический_файл": synthetic_path.name,
        "контрольный_файл": control_path.name,
        "заявок": len(synthetic),
        "строки_совпадают": len(synthetic) == len(control) and not mismatches,
        "уникальных_адресов_для_геокодирования": len(
            {normalized_address(row["Адрес"]) for _, row in synthetic}
        ),
        "бригад_в_контрольном_распределении": len(brigades),
        "контрольных_строк_без_бригады": sum(not row["Бригада"] for _, row in control),
        "статусы_контроля": dict(sorted(status.items())),
        "повторы_номера_в_контроле_строки": duplicate_lines(control),
        "ошибки": problems,
    }
    return result, problems


def audit(directory: Path) -> dict[str, object]:
    regions = {}
    errors: list[str] = []
    for region in REGIONS:
        try:
            result, problems = audit_pair(directory, region)
            regions[region] = result
            errors.extend(f"{region}: {problem}" for problem in problems)
        except (OSError, UnicodeError, ValueError, csv.Error) as error:
            errors.append(str(error))
    return {
        "регионы": regions,
        "ошибки": errors,
        "готовность_к_загрузке": {
            "структура_источников_проверена": not errors,
            "нужны_координаты_адресов": True,
            "нужны_смены_навыки_и_транспорт_бригад": True,
            "контрольные_назначения_не_загружать_как_план": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "Обезличивание",
        help="каталог с шестью исходными CSV",
    )
    args = parser.parse_args()
    result = audit(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["ошибки"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
