from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.models import PlanRunType
from src.schemas.plans import PlanSummary
from src.services.planner import planning_service as service


@pytest.mark.asyncio
async def test_comparison_uses_one_instance_and_commits_both_plans(monkeypatch):
    loaded = SimpleNamespace(instance=object())
    load = AsyncMock(return_value=loaded)
    baseline_result, optimized_result = object(), object()
    baseline = Mock(return_value=baseline_result)
    optimized = AsyncMock(return_value=optimized_result)
    plans = [object(), object()]
    save = AsyncMock(side_effect=plans)
    summaries = [PlanSummary(id=i, run_type=kind, plan_date=date(2026, 8, 17),
                            solver=solver, created_at=datetime.now(timezone.utc),
                            engineers_used=1, assigned_count=1, unassigned_count=0)
                 for i, kind, solver in [(1, 'baseline', 'baseline'), (2, 'optimized', 'cuopt')]]
    summarize = AsyncMock(return_value=summaries)
    monkeypatch.setattr(service, 'load_planning_day', load)
    monkeypatch.setattr(service.baseline_solver, 'solve_day', baseline)
    monkeypatch.setattr(service.cuopt_solver, 'solve_day', optimized)
    monkeypatch.setattr(service, 'save_solution', save)
    monkeypatch.setattr(service, 'summarize_plans', summarize)
    session = SimpleNamespace(commit=AsyncMock())

    result = await service.build_comparison(session, date(2026, 8, 17))

    load.assert_awaited_once_with(session, date(2026, 8, 17))
    baseline.assert_called_once_with(loaded.instance)
    optimized.assert_awaited_once_with(loaded.instance)
    first, second = [call.args for call in save.await_args_list]
    assert first[:5] == (session, loaded, baseline_result, PlanRunType.BASELINE, 'baseline')
    assert second[:5] == (session, loaded, optimized_result, PlanRunType.OPTIMIZED, 'cuopt')
    assert first[5] is not None and first[5] == second[5]
    session.commit.assert_awaited_once()
    summarize.assert_awaited_once_with(session, plans)
    assert result.baseline == summaries[0] and result.optimized == summaries[1]


@pytest.mark.asyncio
async def test_solver_failure_does_not_save_half_a_comparison(monkeypatch):
    monkeypatch.setattr(service, 'load_planning_day', AsyncMock(return_value=SimpleNamespace(instance=object())))
    monkeypatch.setattr(service.baseline_solver, 'solve_day', Mock(return_value=object()))
    monkeypatch.setattr(service.cuopt_solver, 'solve_day', AsyncMock(side_effect=RuntimeError('solver failed')))
    save = AsyncMock()
    monkeypatch.setattr(service, 'save_solution', save)
    session = SimpleNamespace(commit=AsyncMock())
    with pytest.raises(RuntimeError, match='solver failed'):
        await service.build_comparison(session, date(2026, 8, 17))
    save.assert_not_awaited()
    session.commit.assert_not_awaited()
