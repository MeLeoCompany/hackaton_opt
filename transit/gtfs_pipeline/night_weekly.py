"""Явно помеченные недельные шаблоны для собранных ночных маршрутов."""

from datetime import date
from pathlib import Path

from .common import read_json, write_json


def generate_night_weekly(
    catalog_path: Path,
    output_dir: Path,
    template_date: date,
    start_date: date,
    end_date: date,
) -> tuple[int, list[str]]:
    if start_date <= template_date or end_date < start_date:
        raise ValueError("недельный шаблон должен начинаться после точной даты")
    catalog = read_json(catalog_path)
    if catalog["source"]["url"] != "https://transport.mos.ru/transport/schedule/night":
        raise ValueError("нужен каталог ночных автобусов")
    created = 0
    missing = []
    for route in catalog["routes"]:
        route_id = route["source_route_id"]
        template = f"route-{route_id}-{template_date.isoformat()}.json"
        path = output_dir / template
        if not path.is_file():
            missing.append(route["short_name"])
            continue
        exact = read_json(path)
        if (
            exact["kind"] != "bus_exact"
            or exact["route"]["source_route_id"] != route_id
            or exact["source"]["service_date"] != template_date.isoformat()
            or not exact["source"].get("night_service")
        ):
            raise ValueError(f"точный шаблон не соответствует каталогу: {path}")
        write_json(
            output_dir / f"route-{route_id}-weekly.json",
            {
                "schema_version": 1,
                "kind": "bus_weekly",
                "template": template,
                "service": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "weekdays": list(range(7)),
                },
                "source": {
                    "template_date": template_date.isoformat(),
                    "night_service": True,
                    "quality": "приближение",
                    "note": (
                        "Расписание одной ночи повторяется ежедневно до ручного обновления. "
                        "Различия между днями недели не подтверждены."
                    ),
                },
            },
        )
        created += 1
    return created, missing
