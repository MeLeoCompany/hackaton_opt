from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.responses import JSONResponse

from src.schemas.travel import Point, TravelMatrix
from src.services.planner import planner_loader
from src.services.planner.planning_service import snapshot_assignment, snapshot_inputs


@pytest.mark.asyncio
async def test_matrix_rounds_up_and_preserves_unreachable():
    engineer = SimpleNamespace(start_latitude=55.7, start_longitude=37.7, transport_id=1)
    request = SimpleNamespace(latitude=55.71, longitude=37.71)
    matrix = SimpleNamespace(distances_km=[[0, 1], [None, 0]], durations_min=[[0, 10.4], [None, 0]])
    with patch.object(planner_loader, 'build_matrix', AsyncMock(return_value=matrix)):
        distances, times = await planner_loader.build_day_matrices([engineer], [request])
    assert times[1][0, 1] == 11
    assert times[1][1, 0] == planner_loader.UNREACHABLE_MINUTES
    assert distances[1][1, 0] == planner_loader.UNREACHABLE_KM


def test_unreachable_matrix_is_valid_json():
    matrix = TravelMatrix(transport=1, provider='valhalla', points=[Point(latitude=0, longitude=0)],
                          distances_km=[[None]], durations_min=[[None]])
    assert b'null' in JSONResponse(matrix.model_dump(mode='json')).body


def test_snapshot_survives_edits_to_live_data():
    now = datetime(2026, 8, 17, 10, tzinfo=timezone.utc)
    request = SimpleNamespace(id=10, address='original', latitude=55.7, longitude=37.7,
                              window_start=now, window_end=now, duration_minutes=60,
                              priority_id=1, skill_id=2, transport_id=None)
    engineer = SimpleNamespace(id=1, name='original engineer', start_latitude=55.7,
                               start_longitude=37.7, transport_id=1, shift_start=now,
                               shift_end=now, skills=[SimpleNamespace(id=2)])
    snapshot = snapshot_inputs(SimpleNamespace(requests=[request], engineers=[engineer]))
    request.address = 'edited'
    request.duration_minutes = 999
    engineer.transport_id = 2
    assignment = SimpleNamespace(request_id=10, engineer_id=1, visit_order=1,
                                 planned_arrival_time=now, unassigned_reason=None)
    restored = snapshot_assignment(assignment, snapshot)
    assert restored.request.address == 'original'
    assert restored.request.duration_minutes == 60
    assert restored.engineer.transport_id == 1
    assert restored.request.window_start == now
    assert request.address == 'edited'


@pytest.mark.asyncio
async def test_import_reserves_explicit_ids_before_automatic_ids():
    from src.services.requests import requests_service as service
    repository = service.requests_repository
    rows = [dict(id=None, is_active=None), dict(id=1, is_active=None)]
    inserted = set()
    next_id = 1

    def add_request(session, fields):
        nonlocal next_id
        identifier = fields.get('id')
        if identifier is None:
            identifier = next_id
            next_id += 1
        assert identifier not in inserted, 'automatic ID collided with explicit ID'
        inserted.add(identifier)

    async def sync(session):
        nonlocal next_id
        next_id = max(inserted) + 1

    session = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
    with patch.object(repository, 'lock_request_ids', AsyncMock()), \
         patch.object(service, 'load_reference_lookup', AsyncMock()), \
         patch.object(service, 'parse_requests_csv', return_value=SimpleNamespace(rows=rows, errors=[])), \
         patch.object(repository, 'get_requests_by_ids', AsyncMock(return_value={})), \
         patch.object(repository, 'add_request', side_effect=add_request), \
         patch.object(repository, 'sync_request_id_sequence', side_effect=sync):
        report = await service.import_requests_csv(session, b'csv')
    assert inserted == {1, 2}
    assert report.created == 2
    session.commit.assert_awaited_once()
