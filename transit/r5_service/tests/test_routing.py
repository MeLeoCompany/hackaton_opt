from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.routing import build_route_response, local_departure


def settings() -> Settings:
    return Settings(
        osm_path=Path("osm.pbf"),
        gtfs_path=Path("feed.zip"),
        source_wait_seconds=0,
        metro_entry_seconds=240,
        metro_exit_seconds=240,
        reliability_buffer_ratio=0.1,
    )


def test_route_summary_includes_wait_and_metro_penalties() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone(timedelta(hours=3)))
    rows = [
        {
            "segment": 0,
            "transport_mode": "TransportMode.WALK",
            "travel_time": timedelta(minutes=5),
            "wait_time": timedelta(0),
            "distance": 350,
        },
        {
            "segment": 1,
            "transport_mode": "TransportMode.TRANSIT",
            "travel_time": timedelta(minutes=20),
            "wait_time": timedelta(minutes=3),
            "distance": 8_000,
            "route_id": "metro-1",
            "start_stop_id": "a",
            "end_stop_id": "b",
        },
    ]

    result = build_route_response(rows, departure, settings())

    assert result.raw_duration_seconds == 28 * 60
    assert result.entry_exit_penalty_seconds == 8 * 60
    assert result.reliability_buffer_seconds == 216
    assert result.total_duration_seconds == 2376
    assert result.waiting_duration_seconds == 3 * 60
    assert result.transfers == 0


def test_bus_route_does_not_receive_metro_entry_penalty() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    rows = [
        {
            "segment": 0,
            "transport_mode": "TransportMode.TRANSIT",
            "travel_time": timedelta(minutes=10),
            "wait_time": timedelta(minutes=2),
            "route_id": "1054",
        }
    ]

    result = build_route_response(rows, departure, settings())

    assert result.entry_exit_penalty_seconds == 0
    assert result.total_duration_seconds == 792
    assert result.transit_duration_seconds == 600


def test_departure_is_converted_to_moscow_local_time() -> None:
    source = datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc)

    assert local_departure(source) == source.replace(hour=9, minute=30, tzinfo=None)
