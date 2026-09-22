"""Однократная подготовка координат заявок «Востока» через публичный Nominatim.

Соблюдает https://operations.osmfoundation.org/policies/nominatim/ : один поток,
не более запроса в секунду, собственный User-Agent и локальный кеш результатов.
Координаты без подтверждённого номера дома остаются на ручную проверку.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.audit_anonymized import REQUIRED_SYNTHETIC, read_source, source_file

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "hackaton-opt-east-evaluation/0.1 (one-time offline address preparation)"
STREET_TYPES = {
    "пр-кт": "проспект",
    "ул": "улица",
    "пер": "переулок",
    "б-р": "бульвар",
    "наб": "набережная",
    "проезд": "проезд",
    "ш": "шоссе",
    "пл": "площадь",
}


def search_query(address: str) -> str:
    value = address
    value = re.sub(r"^г\.?Город Москва,?\s*", "Москва, ", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:г\.)?Город Москва,?\s*", "Москва, ", value, flags=re.IGNORECASE)
    value = re.sub(
        r"^(?:обл\.)?Московская область,?\s*", "Московская область, ", value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"^МО(?:,|\s)+", "Московская область, ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!\w)г\.\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!\w)пгт\.\s*", "посёлок ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!\w)пр-зд\.?(?=\s|$)", "проезд", value, flags=re.IGNORECASE)
    value = re.sub(
        r"(?:,|\s)([А-Яа-яЁё0-9-]+)\s+ул\.?(?=\s|,)",
        r", улица \1",
        value,
        flags=re.IGNORECASE,
    )
    for short, full in STREET_TYPES.items():
        value = re.sub(
            rf"(?<!\w){re.escape(short)}(?:\.|\s+)",
            full + " ",
            value,
            flags=re.IGNORECASE,
        )
    value = re.sub(r"(?<!\w)д\.\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def house_number(address: str) -> str | None:
    match = re.search(
        r"(?<!\w)д\.\s*(\d+[А-Яа-яA-Za-z/]*(?:\s*к\s*\d+)?(?:\s*стр\.\s*\d+)?)", address
    )
    return match.group(1) if match else None


def canonical_house(value: str) -> str:
    normalized = value.casefold().replace("корпус", "к").replace("строение", "с")
    normalized = normalized.replace("стр.", "с")
    return re.sub(r"[^0-9а-яa-z/]", "", normalized)


def geocode(query: str) -> list[dict]:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 3,
            "countrycodes": "ru",
        }
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pick(address: str, matches: list[dict]) -> dict:
    expected = house_number(address)
    for item in matches:
        actual = item.get("address", {}).get("house_number")
        if (
            expected
            and actual
            and canonical_house(expected) == canonical_house(str(actual))
        ):
            return {
                "status": "exact_house",
                "latitude": round(float(item["lat"]), 6),
                "longitude": round(float(item["lon"]), 6),
                "matched_house": actual,
                "osm_type": item.get("type"),
            }
    return {"status": "review_required" if matches else "not_found"}


def write_cache(path: Path, cache: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def write_review(path: Path, addresses: list[str], cache: dict[str, dict]) -> int:
    """Список адресов, для которых нельзя безопасно строить матрицу маршрутов."""
    unresolved = [
        address
        for address in addresses
        if cache.get(address, {}).get("status") != "exact_house"
    ]
    reviewed: dict[str, tuple[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if row["адрес"] in reviewed:
                    raise ValueError(
                        f"Повторный адрес в списке проверки: {row['адрес']}"
                    )
                reviewed[row["адрес"]] = (
                    row.get("широта_проверенная", ""),
                    row.get("долгота_проверенная", ""),
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            ("адрес", "статус", "широта_проверенная", "долгота_проверенная")
        )
        for address in unresolved:
            latitude, longitude = reviewed.get(address, ("", ""))
            writer.writerow(
                (
                    address,
                    cache.get(address, {}).get("status", "not_checked"),
                    latitude,
                    longitude,
                )
            )
    os.replace(temporary, path)
    return len(unresolved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "Обезличивание")
    parser.add_argument(
        "--cache", type=Path, default=ROOT / "experiments/east/geocodes.json"
    )
    parser.add_argument(
        "--review", type=Path, default=ROOT / "experiments/east/review.csv"
    )
    parser.add_argument("--limit", type=int, help="не более N новых запросов за запуск")
    args = parser.parse_args()
    rows, _ = read_source(
        source_file(args.data_dir, "Восток", "Синтетические данные"), REQUIRED_SYNTHETIC
    )
    addresses = list(dict.fromkeys(row["Адрес"] for _, row in rows))
    cache: dict[str, dict] = (
        json.loads(args.cache.read_text(encoding="utf-8"))
        if args.cache.exists()
        else {}
    )
    last_request = 0.0
    requested = 0
    for address in addresses:
        if address in cache:
            continue
        if args.limit is not None and requested >= args.limit:
            break
        time.sleep(max(0, 1.1 - (time.monotonic() - last_request)))
        try:
            matches = geocode(search_query(address))
        finally:
            last_request = time.monotonic()
        cache[address] = pick(address, matches)
        write_cache(args.cache, cache)
        requested += 1
    statuses = {item["status"] for item in cache.values()}
    counts = {
        status: sum(item["status"] == status for item in cache.values())
        for status in statuses
    }
    print(
        f"Проверено {len(cache)}/{len(addresses)} адресов; за запуск {requested}; результаты: {counts}"
    )
    unresolved = write_review(args.review, addresses, cache)
    print(f"Осталось проверить {unresolved} адресов: {args.review}")
    if len(cache) == len(addresses):
        for address in addresses:
            if cache[address]["status"] != "exact_house":
                print(f"Требует проверки: {address}")


if __name__ == "__main__":
    main()
