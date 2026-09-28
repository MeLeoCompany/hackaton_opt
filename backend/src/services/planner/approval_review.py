"""Невлезшие заявки черновика — перед утверждением (docs/algoV2.md, шаги 2-5).

Первый расчёт дня может не взять часть заявок: не хватило бригад или окна слишком узкие.
Утвердить черновик, пока по невлезшим нет решения, нельзя (planning_service.approve_plan):
иначе заявка молча висит «Новой», пока окно не закроется. Поэтому до утверждения оператор
обзванивает клиентов:

1. preview_approval — второй расчёт с раскрытыми окнами подбирает, когда бригада сможет
   приехать к каждой невлезшей заявке. Ничего не сохраняется;
2. decide_approval — решения оператора (согласованное время, перенос на другой день, отмена)
   применяются к заявкам, и день считается заново тем же решателем и с той же целью. Получается
   новый черновик: оператор смотрит его и утверждает сам — утверждается ровно тот расчёт,
   который он видел.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import clock
from src.core.config import settings
from src.models import Plan
from src.repositories.plans import plans_repository
from src.schemas.plans import (
    PlanSummary,
    ReplanDecision,
    ReplanPreview,
    ReplanProblem,
    SolverName,
)
from src.schemas.system import SolverParams
from src.services.planner import planning_service, replan_service, run_log, window_suggestions
from src.services.planner.objective_policy import DEFAULT_OBJECTIVE_ORDER
from src.services.planner.planning_service import PlanDataError, PlanInUseError


def solver_of(draft: Plan, *, keep_baseline: bool = False) -> SolverName:
    """Чем считать: тем же, чем посчитан черновик. Ярусы базовый алгоритм не умеет,
    поэтому второй расчёт с раскрытыми окнами за него делает cuOpt."""
    try:
        solver = SolverName(draft.solver)
    except ValueError:
        return SolverName.CUOPT
    if solver is SolverName.BASELINE and not keep_baseline:
        return SolverName.CUOPT
    return solver


async def reviewable_draft(session: AsyncSession, plan_id: int, *, office_id: int) -> Plan:
    """Черновик расчёта дня, который ещё можно утвердить."""
    plan = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if plan.approved_at is not None or plan.parent_plan_id is not None or plan.plan_date is None:
        raise PlanInUseError(
            f"Подобрать окна можно только черновику расчёта дня, а план №{plan_id} — не он"
        )
    approved = await plans_repository.get_approved_plan(
        session, plan.plan_date, office_id=office_id
    )
    if approved is not None:
        raise PlanInUseError(
            f"На {plan.plan_date:%d.%m.%Y} уже утверждён план №{approved.id}: невлезшие заявки "
            "решаются при его пересчёте"
        )
    return plan


async def preview_approval(
    session: AsyncSession,
    plan_id: int,
    *,
    office_id: int,
    user_id: int | None = None,
    run_id: UUID | None = None,
    params: SolverParams | None = None,
) -> ReplanPreview:
    """Что предложить клиентам невлезших заявок: второй расчёт с раскрытыми окнами.

    Для черновика базового алгоритма считает cuOpt: базовый не умеет ярусы, а без них
    раскрытые заявки вытеснят те, что уже влезли.
    """
    draft = await reviewable_draft(session, plan_id, office_id=office_id)
    async with run_log.track(
        "approval_preview",
        office_id=office_id,
        plan_date=draft.plan_date,
        solver=solver_of(draft).value,
        user_id=user_id,
        run_id=run_id,
    ):
        unassigned = await planning_service.waiting_unassigned(session, draft)
        counts = await plans_repository.count_assignments_by_plan(session, [draft.id])
        _, assigned_count, _ = counts.get(draft.id, (0, 0, 0))
        suggestions = {}
        if unassigned:
            loaded = await planning_service.load_planning_day(session, draft.plan_date, office_id)
            async with run_log.step("Подбираю время для звонка клиентам (второй расчёт)", 50, 95):
                await run_log.note(
                    f"не влезли в черновик №{draft.id}: "
                    f"{run_log.plural(len(unassigned), 'заявка', 'заявки', 'заявок')}"
                )
                suggestions = await window_suggestions.suggest_windows(
                    loaded,
                    solver_of(draft),
                    tuple(
                        planning_service.objective_order_from_plan(draft) or DEFAULT_OBJECTIVE_ORDER
                    ),
                    {a.request_id for a in unassigned},
                    params=params,
                )
                await run_log.note(
                    f"есть что предложить клиенту: {len(suggestions)} из {len(unassigned)}"
                )
        tolerance = settings.promise_tolerance_minutes
        now = clock.now()
        return ReplanPreview(
            assigned_count=assigned_count,
            promise_tolerance_minutes=tolerance,
            unassigned=[
                problem(a, suggestions.get(a.request_id), tolerance, now) for a in unassigned
            ],
        )


def problem(assignment, suggestion, tolerance_minutes: int, now: datetime) -> ReplanProblem:
    request = assignment.request
    return ReplanProblem(
        request_id=assignment.request_id,
        address=request.address,
        window_start=request.window_start,
        window_end=request.window_end,
        status_id=request.status_id,
        reason=assignment.unassigned_reason or "",
        expired=request.window_end < now,
        suggested_start=suggestion.start if suggestion else None,
        suggested_end=suggestion.start + timedelta(minutes=tolerance_minutes)
        if suggestion
        else None,
        suggested_engineer=suggestion.engineer_name if suggestion else None,
    )


async def decide_approval(
    session: AsyncSession,
    plan_id: int,
    decisions: list[ReplanDecision],
    *,
    office_id: int,
    user_id: int | None = None,
    run_id: UUID | None = None,
    params: SolverParams | None = None,
) -> PlanSummary:
    """Применяет решения по невлезшим заявкам и считает день заново — новым черновиком.

    Решения и расчёт — одна транзакция: не получился расчёт — заявки не меняются.
    Прежний черновик остаётся в списке планов, новый ссылается на него.
    """
    draft = await reviewable_draft(session, plan_id, office_id=office_id)
    if not decisions:
        raise PlanDataError(["решений по заявкам нет — утвердите черновик как есть"])
    waiting = {a.request_id for a in await planning_service.waiting_unassigned(session, draft)}
    stray = sorted({d.request_id for d in decisions} - waiting)
    if stray:
        raise PlanDataError(
            [
                f"заявка №{request_id} не среди невлезших в черновик №{draft.id} — "
                "подберите окна ещё раз"
                for request_id in stray
            ]
        )

    solver = solver_of(draft, keep_baseline=True)
    objective_order = planning_service.objective_order_from_plan(draft) or DEFAULT_OBJECTIVE_ORDER
    async with run_log.track(
        "build",
        office_id=office_id,
        plan_date=draft.plan_date,
        solver=solver.value,
        user_id=user_id,
        run_id=run_id,
    ):
        async with run_log.step("Применяю решения оператора по заявкам", 2, 6):
            await run_log.note(
                f"решения по {run_log.plural(len(decisions), 'заявке', 'заявкам', 'заявкам')} "
                f"из черновика №{draft.id}"
            )
            await replan_service.apply_decisions(
                session,
                draft,
                decisions,
                office_id=office_id,
                user_id=user_id,
                occasion="при утверждении",
            )
        plan = await planning_service.build_inside_run(
            session,
            draft.plan_date,
            solver,
            objective_order,
            office_id=office_id,
            params=params,
        )
        plan.decisions_from_plan_id = draft.id
        plan.decisions_count = len(decisions)
        await session.commit()
        await run_log.attach_plan(plan.id)
        return (await planning_service.summarize_plans(session, [plan]))[0]
