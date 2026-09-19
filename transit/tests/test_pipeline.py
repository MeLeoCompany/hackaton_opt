from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from gtfs_pipeline.gtfs import build_gtfs
from gtfs_pipeline.metro_transfers import (
    TRANSFER_TIME_SECONDS,
    cluster_metro_stations,
    transfer_rows,
)
from gtfs_pipeline.osm_metro import MetroDataError, normalize_line
from gtfs_pipeline.transport_mos import (
    ScheduleParseError,
    collect_bus_route,
    parse_catalog_page,
    parse_route_page,
)
from gtfs_pipeline.validate import validate_gtfs


def _page(second_stop_times: str = '<div class="div10">12</div>') -> str:
    geometry = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": 10,
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [37.1, 55.1]},
                    "properties": {},
                },
                {
                    "id": 11,
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [37.2, 55.2]},
                    "properties": {},
                },
                {
                    "id": 12,
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[37.1, 55.1], [37.2, 55.2]],
                    },
                    "properties": {},
                },
            ],
        }
    )
    return f"""
    <h1 class="h3mb">т1</h1>
    <div class="schedule-route" data-coords='{geometry}'>
      <ul>
        <li data-direction="0" data-stop="1">
          <div class="sl_a"><div class="a_dotted">Начало</div></div>
          <div class="raspisanie_hover">
            <div class="raspisanie_data"><div class="dt1">23:</div>
              <div class="dt2"><div class="div10">58</div></div></div>
            <div class="raspisanie_data"><div class="dt1">00:</div>
              <div class="dt2"><div class="div10">08</div></div></div>
          </div>
        </li>
        <li data-direction="0" data-stop="2">
          <div class="sl_a"><div class="a_dotted">Конец</div></div>
          <div class="raspisanie_hover">
            <div class="raspisanie_data"><div class="dt1">00:</div>
              <div class="dt2">{second_stop_times}<div class="div10">22</div></div></div>
          </div>
        </li>
      </ul>
    </div>
    """


def test_transport_mos_parser_preserves_service_day_order() -> None:
    result = parse_route_page(_page(), route_id=1, service_date=date(2026, 9, 18))

    assert result["stops"][0]["departures"] == [1438, 1448]
    assert result["stops"][1]["departures"] == [1452, 1462]
    assert result["stops"][1]["name"] == "Конец"


def test_transport_mos_parser_rejects_inconsistent_trip_count() -> None:
    with pytest.raises(ScheduleParseError, match="число отправлений различается"):
        parse_route_page(
            _page(second_stop_times=""), route_id=1, service_date=date(2026, 9, 18)
        )


def test_catalog_parser_selects_mode_and_metadata() -> None:
    html = """
    <div id="schedule-table" data-count-pages="20">
      <a class="ts-row" href="/transport/schedule/route/1054">
        <div class="ts-number"><i class="ic ic-bus"></i>е10</div>
        <div class="ts-title">Саларьево — Китай-город</div>
        <div class="ts-200">с 05:00 по 01:00</div>
        <div class="ts-200">каждые 5–10 мин</div>
      </a>
      <a class="ts-row" href="/transport/schedule/route/1048">
        <div class="ts-number"><i class="ic icon-tramway"></i>А</div>
        <div class="ts-title">Калитники — Чистые пруды</div>
      </a>
    </div>
    """

    routes, page_count = parse_catalog_page(html)

    assert page_count == 20
    assert routes[0] == {
        "source_route_id": "1054",
        "short_name": "е10",
        "long_name": "Саларьево — Китай-город",
        "mode": "bus",
        "operating_hours": "с 05:00 по 01:00",
        "interval_summary": "каждые 5–10 мин",
        "url": "https://transport.mos.ru/transport/schedule/route/1054",
    }
    assert routes[1]["mode"] == "other"


def test_route_name_from_catalog_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gtfs_pipeline.transport_mos.fetch_route_page",
        lambda route_id, service_date, direction: _page(),
    )

    route = collect_bus_route(
        1054, date(2026, 9, 19), delay_seconds=0, route_name="е10"
    )

    assert route["route"]["short_name"] == "е10"


def test_checked_in_pilot_builds_valid_gtfs(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "pilot.zip"
    build_gtfs(
        [
            root / "transit/data/bus/e10-2026-09-18.json",
            root / "transit/data/metro/line-1.json",
        ],
        output,
    )

    counts = validate_gtfs(output)
    assert counts["routes.txt"] == 2
    assert counts["trips.txt"] == 1100
    assert counts["stop_times.txt"] == 30245
    with zipfile.ZipFile(output) as archive:
        assert "frequencies.txt" not in archive.namelist()
        assert "calendar_dates.txt" in archive.namelist()
        calendar = archive.read("calendar.txt").decode("utf-8-sig")
        assert "20260101,20261231" in calendar


def test_multiple_dates_of_same_bus_route_do_not_duplicate_route_or_shape(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    first_path = root / "transit/data/bus/e10-2026-09-18.json"
    second = json.loads(first_path.read_text(encoding="utf-8"))
    second["source"]["service_date"] = "2026-09-19"
    second_path = tmp_path / "second-day.json"
    second_path.write_text(json.dumps(second), encoding="utf-8")
    output = tmp_path / "several-days.zip"

    build_gtfs(
        [first_path, second_path, root / "transit/data/metro/line-1.json"], output
    )

    counts = validate_gtfs(output)
    assert counts["routes.txt"] == 2
    assert counts["trips.txt"] == 1318
    assert counts["shapes.txt"] == 1899


def test_all_checked_in_metro_lines_build_valid_gtfs(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    metro = sorted((root / "transit/data/metro").glob("line-*.json"))
    output = tmp_path / "metro.zip"

    build_gtfs(metro, output)

    counts = validate_gtfs(output)
    assert len(metro) == 17
    assert counts["routes.txt"] == 17
    assert counts["trips.txt"] == 14994
    assert "frequencies.txt" not in counts
    assert counts["transfers.txt"] > 0
    with zipfile.ZipFile(output) as archive:
        stops = archive.read("stops.txt").decode("utf-8-sig")
        transfers = archive.read("transfers.txt").decode("utf-8-sig")
        assert "parent_station" in stops
        assert "min_transfer_time" in transfers


def test_metro_normalizer_rejects_single_direction() -> None:
    raw = {
        "elements": [
            {"type": "relation", "id": 1, "tags": {"ref": "1"}, "members": []}
        ]
    }

    with pytest.raises(MetroDataError, match="два направления"):
        normalize_line(raw, relation_ids=[1])


def test_nearby_stops_of_different_lines_form_timed_transfer() -> None:
    def dataset(route_id: str, stop_id: str, name: str, lon: float) -> dict:
        stop = {"source_stop_id": stop_id, "name": name, "lat": 55.75, "lon": lon}
        return {
            "kind": "metro_frequency",
            "route": {"source_route_id": route_id},
            "patterns": [{"stops": [stop]}],
        }

    clusters = cluster_metro_stations(
        [
            dataset("metro-1", "stop-a", "Первая", 37.61),
            dataset("metro-2", "stop-b", "Вторая", 37.6145),
            dataset("metro-1", "stop-c", "Следующая", 37.6055),
        ]
    )
    transfer = next(cluster for cluster in clusters if cluster.is_transfer)

    assert transfer.stop_ids == ("stop-a", "stop-b")
    assert transfer_rows(clusters) == [
        ["stop-a", "stop-b", 2, TRANSFER_TIME_SECONDS],
        ["stop-b", "stop-a", 2, TRANSFER_TIME_SECONDS],
    ]
