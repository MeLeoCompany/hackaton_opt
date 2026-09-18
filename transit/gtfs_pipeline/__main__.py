from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .gtfs import build_gtfs
from .osm_metro import collect_metro_to_file
from .transport_mos import collect_bus_to_file
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
    metro = commands.add_parser("collect-metro", help="получить топологию линии метро")
    metro.add_argument("--relations", required=True, type=int, nargs="+")
    metro.add_argument("--output", required=True, type=Path)
    build = commands.add_parser("build", help="сформировать архив GTFS")
    build.add_argument("inputs", type=Path, nargs="+")
    build.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("validate", help="проверить структуру архива GTFS")
    validate.add_argument("feed", type=Path)
    args = parser.parse_args()

    if args.command == "collect-bus":
        collect_bus_to_file(args.route_id, args.date, args.output)
    elif args.command == "collect-metro":
        collect_metro_to_file(args.relations, args.output)
    elif args.command == "build":
        build_gtfs(args.inputs, args.output)
    elif args.command == "validate":
        for name, count in sorted(validate_gtfs(args.feed).items()):
            print(f"{name}: {count}")


if __name__ == "__main__":
    main()
