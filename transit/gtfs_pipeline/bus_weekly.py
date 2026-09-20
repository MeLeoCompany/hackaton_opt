"""Подготовка повторяемого расписания одного автобусного маршрута."""

from datetime import date
from pathlib import Path

from .common import read_json, write_json
from .transport_mos import collect_bus_to_file


def prepare_bus(
    route_id: int,
    short_name: str,
    weekday_date: date,
    start_date: date,
    end_date: date,
    output_dir: Path,
    *,
    retrospective: bool = False,
) -> Path:
    if not short_name.strip():
        raise ValueError("номер маршрута не может быть пустым")
    if weekday_date.weekday() >= 5:
        raise ValueError("шаблон буднего дня должен быть собран в будний день")
    if end_date < start_date:
        raise ValueError("конец периода повторения раньше начала")
    if start_date < weekday_date and not retrospective:
        raise ValueError("для дат до снимка требуется --retrospective")

    def exact_path(service_date: date) -> Path:
        path = output_dir / f"route-{route_id}-{service_date.isoformat()}.json"
        if not path.is_file():
            collect_bus_to_file(route_id, service_date, path, route_name=short_name)
        data = read_json(path)
        if (
            data.get("kind") != "bus_exact"
            or data.get("route", {}).get("source_route_id") != str(route_id)
            or data["route"].get("short_name") != short_name
            or data.get("source", {}).get("service_date") != service_date.isoformat()
            or {pattern["direction_id"] for pattern in data.get("patterns", [])}
            != {0, 1}
        ):
            raise ValueError(f"неполные или неверные данные маршрута: {path}")
        return path

    template = exact_path(weekday_date)
    output = output_dir / f"route-{route_id}-weekly.json"
    write_json(
        output,
        {
            "schema_version": 1,
            "kind": "bus_weekly",
            "template": template.name,
            "service": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "weekdays": list(range(7)),
            },
            "source": {
                "template_date": weekday_date.isoformat(),
                "quality": "приближение",
                "retrospective": retrospective,
                "note": (
                    "Расписание одного буднего дня повторяется ежедневно. "
                    "Даты до исходного снимка являются ретроспективной оценкой."
                    if retrospective
                    else "Расписание одного буднего дня повторяется ежедневно до ручного обновления."
                ),
            },
        },
    )
    return output
