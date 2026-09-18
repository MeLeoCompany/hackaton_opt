from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from gtfs_pipeline.gtfs import build_gtfs
from gtfs_pipeline.transport_mos import ScheduleParseError, parse_route_page
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
    assert counts["trips.txt"] == 220
    assert counts["stop_times.txt"] == 6485
    with zipfile.ZipFile(output) as archive:
        assert "frequencies.txt" in archive.namelist()
        assert "calendar_dates.txt" in archive.namelist()
