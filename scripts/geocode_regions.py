"""Однократная подготовка координат для одного или нескольких районов."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.audit_anonymized import (
    REGIONS,
    REQUIRED_SYNTHETIC,
    read_source,
    source_file,
)
from scripts.geocode_east import geocode, pick, search_query, write_cache, write_review

ROOT = Path(__file__).resolve().parents[1]
SLUGS = {"Восток": "east", "Юго-восток": "south-east", "Югоцентр": "south-center"}


def prepare_region(data_dir: Path, region: str, *, limit: int | None = None) -> dict[str, int]:
    directory = ROOT / "experiments" / SLUGS[region]
    cache_path = directory / "geocodes.json"
    review_path = directory / "review.csv"
    rows, _ = read_source(
        source_file(data_dir, region, "Синтетические данные"), REQUIRED_SYNTHETIC
    )
    addresses = list(dict.fromkeys(row["Адрес"] for _, row in rows))
    cache: dict[str, dict] = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    requested = 0
    last_request = 0.0
    for address in addresses:
        if address in cache:
            continue
        if limit is not None and requested >= limit:
            break
        time.sleep(max(0, 1.1 - (time.monotonic() - last_request)))
        try:
            matches = geocode(search_query(address))
        finally:
            last_request = time.monotonic()
        cache[address] = pick(address, matches)
        write_cache(cache_path, cache)
        requested += 1
    unresolved = write_review(review_path, addresses, cache)
    return {
        "addresses": len(addresses),
        "checked": len(cache),
        "requested": requested,
        "exact": sum(item["status"] == "exact_house" for item in cache.values()),
        "review": unresolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("regions", nargs="+", choices=REGIONS)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "Обезличивание")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    for region in args.regions:
        result = prepare_region(args.data_dir, region, limit=args.limit)
        print(
            f"{region}: проверено {result['checked']}/{result['addresses']}; "
            f"точно {result['exact']}; ручная проверка {result['review']}; "
            f"новых запросов {result['requested']}"
        )


if __name__ == "__main__":
    main()
