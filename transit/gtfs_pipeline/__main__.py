from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .gtfs import build_gtfs
from .osm_metro import collect_metro_network, collect_metro_to_file
from .transport_mos import (
    collect_bus_batch,
    collect_bus_to_file,
    collect_catalog_to_file,
)
from .validate import validate_gtfs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сбор и формирование пилотного набора GTFS для Москвы"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bus = commands.add_parser("collect-bus", help="получить расписание автобуса")
    bus.add_argument("--route-id", required=True, type=int)
    bus.add_argument("--date", required=True, type=date.fromisoformat)
    bus.add_argument("--output", required=True, type=Path)
    catalog = commands.add_parser(
        "collect-bus-catalog", help="получить каталог автобусных маршрутов"
    )
    catalog.add_argument("--output", required=True, type=Path)
    catalog.add_argument(
        "--cache-dir",
        type=Path,
        help="каталог кеша страниц для продолжения после сетевого сбоя",
    )
    batch = commands.add_parser(
        "collect-bus-batch", help="пакетно получить выбранные маршруты и даты"
    )
    batch.add_argument("--route-id", required=True, type=int, nargs="+")
    batch.add_argument("--date", required=True, type=date.fromisoformat, nargs="+")
    batch.add_argument("--output-dir", required=True, type=Path)
    batch.add_argument(
        "--catalog", type=Path, help="каталог для проверки ID и названий маршрутов"
    )
    metro = commands.add_parser("collect-metro", help="получить топологию линии метро")
    metro.add_argument("--relations", required=True, type=int, nargs="+")
    metro.add_argument("--output", required=True, type=Path)
    metro_network = commands.add_parser(
        "collect-metro-network", help="получить топологию всех линий метро"
    )
    metro_network.add_argument("--output-dir", required=True, type=Path)
    metro_network.add_argument(
        "--cache-dir", type=Path, help="кеш ответов Overpass для продолжения после сбоя"
    )
    build = commands.add_parser("build", help="сформировать архив GTFS")
    build.add_argument("inputs", type=Path, nargs="+")
    build.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("validate", help="проверить структуру архива GTFS")
    validate.add_argument("feed", type=Path)
    args = parser.parse_args()

    if args.command == "collect-bus":
        collect_bus_to_file(args.route_id, args.date, args.output)
    elif args.command == "collect-bus-catalog":
        collect_catalog_to_file(args.output, args.cache_dir)
    elif args.command == "collect-bus-batch":
        report = collect_bus_batch(
            args.route_id, args.date, args.output_dir, catalog_path=args.catalog
        )
        print(f"Успешно: {report['successful']}; с ошибкой: {report['failed']}")
        if report["failed"]:
            raise SystemExit(1)
    elif args.command == "collect-metro":
        collect_metro_to_file(args.relations, args.output)
    elif args.command == "collect-metro-network":
        report = collect_metro_network(args.output_dir, args.cache_dir)
        print(f"Собрано линий: {report['line_count']}")
    elif args.command == "build":
        build_gtfs(args.inputs, args.output)
    elif args.command == "validate":
        for name, count in sorted(validate_gtfs(args.feed).items()):
            print(f"{name}: {count}")


if __name__ == "__main__":
    main()
