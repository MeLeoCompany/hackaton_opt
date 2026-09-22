from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from gtfs_pipeline.bus_weekly import prepare_bus
from gtfs_pipeline.gtfs import build_gtfs
from gtfs_pipeline.local_bus import import_bus_html
from gtfs_pipeline.metro_transfers import (
    TRANSFER_TIME_SECONDS,
    cluster_metro_stations,
    transfer_rows,
)
from gtfs_pipeline.night_weekly import generate_night_weekly
from gtfs_pipeline.osm_metro import MetroDataError, normalize_line
from gtfs_pipeline.transport_mos import (
    ScheduleParseError,
    _align_circular_departures,
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


def test_circular_bus_parser_aligns_trips_after_control_stop_reset() -> None:
    stops = [
        {"departures": [180, 195, 210, 225]},
        {"departures": [194, 209, 224, 239]},
        # На контрольной остановке портал снова начинает с первого рейса.
        {"departures": [180, 195, 210, 225]},
    ]

    _align_circular_departures(stops)

    assert stops[2]["departures"] == [195, 210, 225, 1620]


def test_night_bus_parser_keeps_morning_departures_on_next_day() -> None:
    html = _page().replace('<div class="dt1">00:', '<div class="dt1">05:')

    result = parse_route_page(
        html, route_id=1335, service_date=date(2026, 9, 20), night=True
    )

    assert result["stops"][0]["departures"] == [1438, 1748]
    assert result["stops"][1]["departures"] == [1752, 1762]


def test_night_bus_gtfs_keeps_service_date_across_midnight(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    source = root / "transit/data/bus/night/route-1335-2026-09-20.json"
    output = tmp_path / "night.zip"

    build_gtfs([source], output)

    validate_gtfs(output)
    with zipfile.ZipFile(output) as archive:
        stop_times = archive.read("stop_times.txt").decode("utf-8-sig")
        exceptions = archive.read("calendar_dates.txt").decode("utf-8-sig")
        assert "29:" in stop_times
        assert "20260920" in exceptions
        assert "bus-1335-2026-09-20-morning,20260921,1" in exceptions
        assert ",00:10:00,00:10:00," in stop_times


def test_night_weekly_repeats_only_checked_in_routes(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    source = root / "transit/data/bus/night/route-1335-2026-09-20.json"
    (tmp_path / source.name).write_bytes(source.read_bytes())
    catalog = {
        "source": {"url": "https://transport.mos.ru/transport/schedule/night"},
        "routes": [
            {"source_route_id": "1335", "short_name": "н1"},
            {"source_route_id": "1336", "short_name": "н2"},
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    created, missing = generate_night_weekly(
        catalog_path,
        tmp_path,
        date(2026, 9, 20),
        date(2026, 8, 1),
        date(2026, 12, 31),
        retrospective=True,
    )

    assert created == 1
    assert missing == ["н2"]
    output = tmp_path / "weekly.zip"
    build_gtfs([source, tmp_path / "route-1335-weekly.json"], output)
    validate_gtfs(output)
    with zipfile.ZipFile(output) as archive:
        calendar = archive.read("calendar.txt").decode("utf-8-sig")
        assert "bus-1335-weekly-2026-08-01-0-1-2-3-4-5-6-morning" in calendar


def test_prepare_bus_requires_both_directions_and_repeats_daily(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    source = root / "transit/data/bus/route-1048-2026-09-18.json"
    (tmp_path / source.name).write_bytes(source.read_bytes())

    created = prepare_bus(
        1048,
        "А",
        date(2026, 9, 18),
        date(2026, 8, 1),
        date(2026, 12, 31),
        tmp_path,
        retrospective=True,
    )

    weekly = json.loads(created.read_text())
    assert weekly["template"] == source.name
    assert weekly["service"]["weekdays"] == list(range(7))
    assert "приближение" == weekly["source"]["quality"]
    assert weekly["source"]["retrospective"] is True
    output = tmp_path / "bus.zip"
    build_gtfs([source, created], output)
    validate_gtfs(output)

    broken = json.loads((tmp_path / source.name).read_text())
    broken["patterns"].pop()
    (tmp_path / source.name).write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="неполные"):
        prepare_bus(
            1048,
            "А",
            date(2026, 9, 18),
            date(2026, 9, 21),
            date(2026, 12, 31),
            tmp_path,
        )


def test_prepare_bus_accepts_one_closed_circular_direction(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    source = root / "transit/data/bus/route-1048-2026-09-18.json"
    data = json.loads(source.read_text())
    data["route"]["source_route_id"] = "1049"
    data["route"]["short_name"] = "Б"
    data["source"]["service_date"] = "2026-09-22"
    data["patterns"] = data["patterns"][:1]
    data["patterns"][0]["shape"][-1] = data["patterns"][0]["shape"][0]
    exact = tmp_path / "route-1049-2026-09-22.json"
    exact.write_text(json.dumps(data), encoding="utf-8")

    created = prepare_bus(
        1049,
        "Б",
        date(2026, 9, 22),
        date(2026, 8, 1),
        date(2026, 12, 31),
        tmp_path,
        retrospective=True,
    )

    assert created.is_file()


def test_import_bus_html_creates_schedule_and_archives_sources(tmp_path: Path) -> None:
    incoming = tmp_path / "new"
    archive = tmp_path / "added"
    output = tmp_path / "data"
    incoming.mkdir()
    page = _page().replace(
        'data-direction="0" data-stop="1"',
        'data-direction="0" data-route="42" data-date="2026-09-22" data-stop="1"',
    )
    (incoming / "т1 - 1.html").write_text(page, encoding="utf-8")
    reverse = page.replace('data-direction="0"', 'data-direction="1"')
    (incoming / "т1 - 2.html").write_text(reverse, encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "routes": [
                    {"source_route_id": "42", "short_name": "т1", "mode": "bus"}
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory = tmp_path / "bus_names.txt"
    inventory.write_text("А\n", encoding="utf-8")

    imported = import_bus_html(
        incoming,
        archive,
        catalog,
        output,
        date(2026, 8, 1),
        date(2026, 12, 31),
        inventory,
    )

    assert imported == ["т1"]
    assert (output / "route-42-2026-09-22.json").is_file()
    assert (output / "route-42-weekly.json").is_file()
    assert sorted(path.name for path in archive.iterdir()) == [
        "т1 - 1.html",
        "т1 - 2.html",
    ]
    assert not list(incoming.iterdir())
    assert inventory.read_text(encoding="utf-8") == "А\nт1\n"


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


def test_weekly_bus_calendar_keeps_exact_days_and_repeats_until_expiry(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    bus = root / "transit/data/bus"
    output = tmp_path / "weekly.zip"
    build_gtfs(
        [
            bus / "e10-2026-09-18.json",
            bus / "route-1054-2026-09-19.json",
            bus / "route-1054-2026-09-20.json",
            bus / "e10-weekday-weekly.json",
            bus / "e10-weekend-weekly.json",
        ],
        output,
    )

    validate_gtfs(output)
    with zipfile.ZipFile(output) as archive:

        def rows(name: str) -> list[dict[str, str]]:
            return list(
                csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")))
            )

        calendars = rows("calendar.txt")
        assert len(calendars) == 2
        assert {
            tuple(row[day] for day in ("monday", "friday", "saturday", "sunday"))
            for row in calendars
        } == {
            ("1", "1", "0", "0"),
            ("0", "0", "1", "1"),
        }
        assert {row["end_date"] for row in calendars} == {"20261231"}
        assert {row["start_date"] for row in calendars} == {"20260801"}
        assert any(
            row["monday"] == "1" and row["start_date"] <= "20260817" <= row["end_date"]
            for row in calendars
        )
        exceptions = rows("calendar_dates.txt")
        assert len(exceptions) == 6
        assert Counter(row["exception_type"] for row in exceptions) == {"1": 3, "2": 3}
        trips = rows("trips.txt")
        assert len({row["trip_id"] for row in trips}) == len(trips)


def test_exact_bus_day_overrides_weekly_template(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    sample = root / "transit/data/bus/e10-2026-09-18.json"
    manifest = {
        "kind": "bus_weekly",
        "template": str(sample),
        "service": {
            "start_date": "2026-09-18",
            "end_date": "2026-09-25",
            "weekdays": [4],
        },
        "source": {"quality": "приближение"},
    }
    path = tmp_path / "weekly.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "override.zip"
    build_gtfs([sample, path], output)

    with zipfile.ZipFile(output) as archive:
        exceptions = list(
            csv.DictReader(
                io.StringIO(archive.read("calendar_dates.txt").decode("utf-8-sig"))
            )
        )
    assert {(row["date"], row["exception_type"]) for row in exceptions} == {
        ("20260918", "1"),
        ("20260918", "2"),
    }


def test_backdated_bus_calendar_requires_explicit_retrospective_mark(
    tmp_path: Path,
) -> None:
    source = Path(__file__).parents[2] / "transit/data/bus/e10-weekday-weekly.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["source"].pop("retrospective")
    path = tmp_path / "e10-weekday-weekly.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    template = source.parent / manifest["template"]
    (tmp_path / template.name).write_bytes(template.read_bytes())
    with pytest.raises(ValueError, match="ретроспективное"):
        build_gtfs([path], tmp_path / "invalid.zip")


def test_weekly_bus_rejects_different_control_day(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    bus = root / "transit/data/bus"
    manifest = json.loads((bus / "e10-weekend-weekly.json").read_text(encoding="utf-8"))
    manifest["template"] = str(bus / "route-1054-2026-09-19.json")
    manifest["matching_examples"] = [str(bus / "e10-2026-09-18.json")]
    path = tmp_path / "weekly.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="контрольная дата отличается"):
        build_gtfs([path], tmp_path / "bad.zip")


def test_all_checked_in_metro_lines_build_valid_gtfs(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    metro = sorted((root / "transit/data/metro").glob("line-*.json"))
    output = tmp_path / "metro.zip"

    build_gtfs(metro, output)

    counts = validate_gtfs(output)
    assert len(metro) == 18
    assert counts["routes.txt"] == 18
    assert counts["trips.txt"] == 15402
    assert "frequencies.txt" not in counts
    assert counts["transfers.txt"] > 0
    with zipfile.ZipFile(output) as archive:
        routes = archive.read("routes.txt").decode("utf-8-sig")
        stops = archive.read("stops.txt").decode("utf-8-sig")
        transfers = archive.read("transfers.txt").decode("utf-8-sig")
        assert "mcc-14" in routes
        assert "parent_station" in stops
        assert "min_transfer_time" in transfers


def test_mcc_has_both_closed_directions_and_metro_transfers() -> None:
    root = Path(__file__).parents[2]
    paths = [
        root / "transit/data/metro/line-14-mcc.json",
        root / "transit/data/metro/line-1.json",
    ]
    datasets = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    mcc = datasets[0]

    assert mcc["route"]["route_type"] == 2
    assert len(mcc["patterns"]) == 2
    assert all(
        len(pattern["stops"]) == 32
        and pattern["stops"][0]["source_stop_id"]
        == pattern["stops"][-1]["source_stop_id"]
        for pattern in mcc["patterns"]
    )
    assert any(
        {"mcc-14", "metro-1"} <= set(cluster.routes)
        for cluster in cluster_metro_stations(datasets)
    )


def test_metro_normalizer_rejects_single_direction() -> None:
    raw = {
        "elements": [{"type": "relation", "id": 1, "tags": {"ref": "1"}, "members": []}]
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
