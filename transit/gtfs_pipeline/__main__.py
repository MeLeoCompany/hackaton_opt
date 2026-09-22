from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .bus_weekly import prepare_bus
from .gtfs import build_gtfs
from .local_bus import import_bus_html
from .night_weekly import generate_night_weekly
from .osm_mcc import collect_mcc_to_file
from .osm_metro import collect_metro_network, collect_metro_to_file
from .transport_mos import (
    collect_bus_batch,
    collect_bus_to_file,
    collect_catalog_to_file,
    collect_night_catalog_to_file,
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
    night_catalog = commands.add_parser(
        "collect-night-catalog", help="получить список ночных автобусов"
    )
    night_catalog.add_argument("--output", required=True, type=Path)
    batch = commands.add_parser(
        "collect-bus-batch", help="пакетно получить выбранные маршруты и даты"
    )
    batch.add_argument("--route-id", required=True, type=int, nargs="+")
    batch.add_argument("--date", required=True, type=date.fromisoformat, nargs="+")
    batch.add_argument("--output-dir", required=True, type=Path)
    batch.add_argument(
        "--catalog", type=Path, help="каталог для проверки ID и названий маршрутов"
    )
    prepared_bus = commands.add_parser(
        "prepare-bus",
        help="получить оба направления и создать ежедневный шаблон автобуса",
    )
    prepared_bus.add_argument("--route-id", required=True, type=int)
    prepared_bus.add_argument("--short-name", required=True)
    prepared_bus.add_argument("--weekday-date", required=True, type=date.fromisoformat)
    prepared_bus.add_argument("--start-date", required=True, type=date.fromisoformat)
    prepared_bus.add_argument("--end-date", required=True, type=date.fromisoformat)
    prepared_bus.add_argument("--retrospective", action="store_true")
    prepared_bus.add_argument("--output-dir", required=True, type=Path)
    local_bus = commands.add_parser(
        "import-bus-html",
        help="импортировать сохранённые HTML двух направлений автобуса",
    )
    local_bus.add_argument("--input-dir", required=True, type=Path)
    local_bus.add_argument("--archive-dir", required=True, type=Path)
    local_bus.add_argument("--catalog", required=True, type=Path)
    local_bus.add_argument("--output-dir", required=True, type=Path)
    local_bus.add_argument("--inventory", type=Path)
    local_bus.add_argument("--start-date", required=True, type=date.fromisoformat)
    local_bus.add_argument("--end-date", required=True, type=date.fromisoformat)
    night_batch = commands.add_parser(
        "collect-night-bus-batch", help="получить все ночные автобусы из каталога"
    )
    night_batch.add_argument("--catalog", required=True, type=Path)
    night_batch.add_argument(
        "--date", required=True, type=date.fromisoformat, nargs="+"
    )
    night_batch.add_argument("--output-dir", required=True, type=Path)
    night_weekly = commands.add_parser(
        "repeat-night-buses", help="повторять собранные ночные рейсы по дням"
    )
    night_weekly.add_argument("--catalog", required=True, type=Path)
    night_weekly.add_argument("--template-date", required=True, type=date.fromisoformat)
    night_weekly.add_argument("--start-date", required=True, type=date.fromisoformat)
    night_weekly.add_argument("--end-date", required=True, type=date.fromisoformat)
    night_weekly.add_argument("--retrospective", action="store_true")
    night_weekly.add_argument("--output-dir", required=True, type=Path)
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
    mcc = commands.add_parser("collect-mcc", help="получить обе стороны МЦК")
    mcc.add_argument("--output", required=True, type=Path)
    build = commands.add_parser("build", help="сформировать архив GTFS")
    build.add_argument("inputs", type=Path, nargs="+")
    build.add_argument("--output", required=True, type=Path)
    pilot = commands.add_parser(
        "build-pilot", help="собрать весь локальный пилотный GTFS"
    )
    pilot.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("validate", help="проверить структуру архива GTFS")
    validate.add_argument("feed", type=Path)
    args = parser.parse_args()

    if args.command == "collect-bus":
        collect_bus_to_file(args.route_id, args.date, args.output)
    elif args.command == "collect-bus-catalog":
        collect_catalog_to_file(args.output, args.cache_dir)
    elif args.command == "collect-night-catalog":
        collect_night_catalog_to_file(args.output)
    elif args.command == "collect-bus-batch":
        report = collect_bus_batch(
            args.route_id, args.date, args.output_dir, catalog_path=args.catalog
        )
        print(f"Успешно: {report['successful']}; с ошибкой: {report['failed']}")
        if report["failed"]:
            raise SystemExit(1)
    elif args.command == "prepare-bus":
        output = prepare_bus(
            args.route_id,
            args.short_name,
            args.weekday_date,
            args.start_date,
            args.end_date,
            args.output_dir,
            retrospective=args.retrospective,
        )
        print(f"Создан ежедневный шаблон: {output}")
    elif args.command == "import-bus-html":
        imported = import_bus_html(
            args.input_dir,
            args.archive_dir,
            args.catalog,
            args.output_dir,
            args.start_date,
            args.end_date,
            inventory_path=args.inventory,
        )
        print(f"Импортировано маршрутов: {len(imported)} ({', '.join(imported)})")
    elif args.command == "collect-night-bus-batch":
        from .common import read_json

        catalog = read_json(args.catalog)
        if (
            catalog["source"]["url"]
            != "https://transport.mos.ru/transport/schedule/night"
        ):
            raise ValueError("нужен каталог ночных автобусов")
        route_ids = [int(route["source_route_id"]) for route in catalog["routes"]]
        report = collect_bus_batch(
            route_ids, args.date, args.output_dir, catalog_path=args.catalog, night=True
        )
        print(f"Успешно: {report['successful']}; с ошибкой: {report['failed']}")
        if report["failed"]:
            raise SystemExit(1)
    elif args.command == "repeat-night-buses":
        created, missing = generate_night_weekly(
            args.catalog,
            args.output_dir,
            args.template_date,
            args.start_date,
            args.end_date,
            retrospective=args.retrospective,
        )
        print(f"Создано недельных шаблонов: {created}")
        if missing:
            print(f"Без полного расписания: {', '.join(missing)}")
    elif args.command == "collect-metro":
        collect_metro_to_file(args.relations, args.output)
    elif args.command == "collect-metro-network":
        report = collect_metro_network(args.output_dir, args.cache_dir)
        print(f"Собрано линий: {report['line_count']}")
    elif args.command == "collect-mcc":
        collect_mcc_to_file(args.output)
    elif args.command == "build":
        build_gtfs(args.inputs, args.output)
    elif args.command == "build-pilot":
        root = Path(__file__).parents[1] / "data"
        inputs = sorted((root / "bus").glob("route-*.json"))
        inputs += sorted((root / "bus").glob("e10-*.json"))
        inputs += sorted((root / "bus" / "night").glob("route-*.json"))
        inputs += sorted((root / "metro").glob("line-*.json"))
        if not inputs:
            raise ValueError("локальные данные для GTFS не найдены")
        build_gtfs(inputs, args.output)
    elif args.command == "validate":
        for name, count in sorted(validate_gtfs(args.feed).items()):
            print(f"{name}: {count}")


if __name__ == "__main__":
    main()
