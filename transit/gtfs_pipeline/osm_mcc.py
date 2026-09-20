"""Расчётное расписание МЦК поверх двух направленных отношений OSM."""

from pathlib import Path

from .common import write_json
from .osm_metro import fetch_line, normalize_line

MCC_RELATIONS = [6548266, 6548267]
OFFICIAL_FAQ_URL = "https://transport.mos.ru/transport/faq"


def collect_mcc_to_file(output: Path) -> None:
    dataset = normalize_line(fetch_line(MCC_RELATIONS), relation_ids=MCC_RELATIONS)
    if any(len(pattern["stops"]) != 32 for pattern in dataset["patterns"]):
        raise ValueError("в МЦК ожидались две кольцевые трассы по 31 станции")
    if any(
        pattern["stops"][0]["source_stop_id"] != pattern["stops"][-1]["source_stop_id"]
        for pattern in dataset["patterns"]
    ):
        raise ValueError("трасса МЦК должна замыкаться в кольцо")

    dataset["route"].update(
        source_route_id="mcc-14",
        short_name="МЦК",
        long_name="Московское центральное кольцо",
        route_type=2,
        color="E87EA1",
    )
    dataset["source"].update(
        operating_hours_url=OFFICIAL_FAQ_URL,
        headways_url=OFFICIAL_FAQ_URL,
        color_note="Цвет выбран для отображения МЦК в интерфейсе.",
    )
    dataset["service"].update(
        official_operating_window=["05:30:00", "25:00:00"],
        headways=[
            {"start": "05:30:00", "end": "06:30:00", "seconds": 480},
            {"start": "06:30:00", "end": "10:00:00", "seconds": 240},
            {"start": "10:00:00", "end": "16:00:00", "seconds": 480},
            {"start": "16:00:00", "end": "20:00:00", "seconds": 240},
            {"start": "20:00:00", "end": "25:00:00", "seconds": 480},
        ],
        headway_note=(
            "Официальные интервалы: 4 минуты в часы пик, 8 минут в остальное время. "
            "Границы часов пик и конкретные отправления приняты для расчёта."
        ),
        duration_note="88 минут на полный круг из направленных отношений OSM.",
    )
    write_json(output, dataset)
