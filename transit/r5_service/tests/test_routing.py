from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.config import Settings
from app.models import MatrixPoint
from app.routing import (
    build_matrix_block_response,
    build_matrix_response,
    build_route_response,
    local_departure,
)


def settings() -> Settings:
    return Settings(
        osm_path=Path("osm.pbf"),
        gtfs_path=Path("feed.zip"),
        source_wait_seconds=0,
        metro_entry_seconds=240,
        metro_exit_seconds=240,
        walking_speed_kmh=4.8,
        reliability_buffer_ratio=0.1,
        matrix_max_points=100,
        matrix_block_max_pairs=2500,
        matrix_time_window_minutes=10,
        max_travel_minutes=240,
    )


@pytest.mark.parametrize("speed", ["0", "nan", "11"])
def test_invalid_walking_speed_is_rejected(monkeypatch, speed: str) -> None:
    monkeypatch.setenv("R5_WALKING_SPEED_KMH", speed)

    with pytest.raises(ValueError, match="R5_WALKING_SPEED_KMH"):
        Settings.from_env()


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


def test_mcc_route_receives_station_entry_penalty() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    rows = [
        {
            "segment": 0,
            "transport_mode": "TransportMode.RAIL",
            "travel_time": 600,
            "route_id": "mcc-14",
        }
    ]

    result = build_route_response(rows, departure, settings())

    assert result.entry_exit_penalty_seconds == 480


def test_same_metro_line_split_into_segments_is_not_an_extra_transfer() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    rows = [
        {
            "segment": 0,
            "transport_mode": "TransportMode.SUBWAY",
            "route_id": "metro-1",
            "travel_time": 180,
        },
        {"segment": 1, "transport_mode": "TransportMode.WALK", "travel_time": 120},
        {
            "segment": 2,
            "transport_mode": "TransportMode.SUBWAY",
            "route_id": "metro-5",
            "travel_time": 300,
        },
        {
            "segment": 3,
            "transport_mode": "TransportMode.SUBWAY",
            "route_id": "metro-5",
            "travel_time": 240,
        },
    ]

    result = build_route_response(rows, departure, settings())

    assert result.transfers == 1


def test_departure_is_converted_to_moscow_local_time() -> None:
    source = datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc)

    assert local_departure(source) == source.replace(hour=9, minute=30, tzinfo=None)


def test_matrix_preserves_point_order_and_marks_unreachable_pairs() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    points = [
        MatrixPoint(id="engineer-7", lat=55.78, lon=37.68),
        MatrixPoint(id="request-42", lat=55.69, lon=37.53),
        MatrixPoint(id="request-43", lat=55.75, lon=37.61),
    ]
    rows = [
        {"from_id": "engineer-7", "to_id": "request-42", "travel_time": 24},
        {"from_id": "request-42", "to_id": "engineer-7", "travel_time": 25.5},
        {"from_id": "engineer-7", "to_id": "request-43", "travel_time": float("nan")},
    ]

    result = build_matrix_response(rows, points, departure, settings())

    assert result.point_ids == ["engineer-7", "request-42", "request-43"]
    assert result.raw_durations_seconds == [
        [0, 1440, None],
        [1530, 0, None],
        [None, None, 0],
    ]
    assert result.durations_seconds == [
        [0, 1584, None],
        [1683, 0, None],
        [None, None, 0],
    ]


def test_matrix_ignores_rows_with_unknown_point_ids() -> None:
    departure = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    points = [
        MatrixPoint(id="a", lat=55.7, lon=37.6),
        MatrixPoint(id="b", lat=55.8, lon=37.7),
    ]

    result = build_matrix_response(
        [{"from_id": "unknown", "to_id": "a", "travel_time": 5}],
        points,
        departure,
        settings(),
    )

    assert result.raw_durations_seconds == [[0, None], [None, 0]]


def test_rectangular_block_preserves_direction_and_missing_pairs() -> None:
    departure = datetime(2026, 9, 18, 9, tzinfo=timezone.utc)
    origins = [
        MatrixPoint(id="a", lat=55.7, lon=37.6),
        MatrixPoint(id="b", lat=55.8, lon=37.7),
    ]
    destinations = [
        MatrixPoint(id="b", lat=55.8, lon=37.7),
        MatrixPoint(id="c", lat=55.9, lon=37.8),
    ]
    result = build_matrix_block_response(
        [{"from_id": "a", "to_id": "c", "travel_time": 12}],
        origins,
        destinations,
        departure,
        settings(),
    )

    assert result.origin_ids == ["a", "b"]
    assert result.destination_ids == ["b", "c"]
    assert result.raw_durations_seconds == [[None, 720], [0, None]]
    assert result.durations_seconds == [[None, 792], [0, None]]
