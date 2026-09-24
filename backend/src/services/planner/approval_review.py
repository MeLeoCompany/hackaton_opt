"""Невлезшие заявки черновика — перед утверждением (docs/algoV2.md, шаги 2-5).

Первый расчёт дня может не взять часть заявок: не хватило бригад или окна слишком узкие.
Утвердить черновик, пока по невлезшим нет решения, нельзя (planning_service.approve_plan):
иначе заявка молча висит «Новой», пока окно не закроется. Поэтому до утверждения оператор
обзванивает клиентов:

1. preview_approval — список невлезших заявок; с suggest второй расчёт с раскрытыми окнами
   подбирает, когда бригада сможет приехать к каждой. Ничего не сохраняется;
2. decide_approval — решения оператора применяются к заявкам. Перенос и отмена только убирают
   работу из дня: маршруты те же, расчёта нет, черновик утверждается как есть. Согласие на
   предложенное время добавляет работу — тогда день считается заново тем же решателем и с той
   же целью, и новый черновик оператор смотрит и утверждает сам.
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


async def reviewable_plan(session: AsyncSession, plan_id: int, *, office_id: int) -> Plan:
    """Расчёт, по невлезшим заявкам которого ещё можно принимать решения.

    Это и черновик дня, и пересчёт действующего плана: круг у них один, и решается в нём одно
    и то же — кому подобрать окно, кого перенести, кого отменить (docs/algoV2.md, шаги 2-5).
    """
    plan = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if plan.approved_at is not None or plan.plan_date is None:
        raise PlanInUseError(
            f"Решать по невлезшим заявкам можно у неутверждённого расчёта, а план №{plan_id} — не он"
        )
    if getattr(plan, "parent_plan_id", None) is not None:
        return await reviewable_replan(session, plan)
    approved = await plans_repository.get_approved_plan(
        session, plan.plan_date, office_id=office_id
    )
    if approved is not None:
        raise PlanInUseError(
            f"На {plan.plan_date:%d.%m.%Y} уже утверждён план №{approved.id}: невлезшие заявки "
            "решаются при его пересчёте"
        )
    # черновик идущего дня живёт до своего момента выезда: после него подбирать окна и
    # применять решения уже некуда — день считают заново (docs/algoV2.md, шаги 1 и 6)
    stale = await planning_service.draft_stale_reason(session, plan)
    if stale:
        raise PlanInUseError(stale)
    return plan


async def reviewable_replan(session: AsyncSession, plan: Plan) -> Plan:
    """Пересчёт, который ещё в игре: не вступил в силу сам и не признан недействительным.

    Пересчёт вступает в силу в свой момент (replan_autoapply), так что решения по невлезшим
    оператор принимает до него. Не успел — заявки останутся «Новыми», это штатный исход
    (docs/algoV2.md, шаг 6).
    """
    if getattr(plan, "voided_at", None) is not None:
        raise PlanInUseError(
            f"Пересчёт №{plan.id} не вступил в силу: {plan.void_reason or 'день изменился'}. "
            "Пересчитайте план заново"
        )
    parent = await plans_repository.get_plan(session, plan.parent_plan_id)
    current = await plans_repository.get_approved_plan(
        session, plan.plan_date, office_id=plan.office_id
    )
    if parent is None or current is None or current.id != parent.id:
        raise PlanInUseError(
            f"Пересчёт №{plan.id} устарел: действующий план дня уже не №{plan.parent_plan_id}. "
            "Пересчитайте действующий план заново"
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
    suggest: bool = True,
) -> ReplanPreview:
    """Что предложить клиентам невлезших заявок: второй расчёт с раскрытыми окнами.

    Для черновика базового алгоритма считает cuOpt: базовый не умеет ярусы, а без них
    раскрытые заявки вытеснят те, что уже влезли.
    """
    draft = await reviewable_plan(session, plan_id, office_id=office_id)
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
        if unassigned and suggest:
            loaded = await day_of(session, draft, office_id)
            async with run_log.step("Подбираю время для звонка клиентам (второй расчёт)", 50, 95):
                await run_log.note(
                    f"не влезли в расчёт №{draft.id}: "
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


async def day_of(session: AsyncSession, plan: Plan, office_id: int):
    """День, по которому подбираются окна: у черновика — весь день, у пересчёта — его остаток.

    Второй расчёт идёт на выезд через запас: бригады свободны не раньше него. У пересчёта они
    к тому же стоят там, где они сейчас, и заняты начатой работой — иначе предложенное клиенту
    время было бы не про этот день (docs/algoV2.md, шаг 2).
    """
    at = planning_service.departure_moment(plan.plan_date)
    if getattr(plan, "parent_plan_id", None) is None:
        return await planning_service.load_planning_day(
            session, plan.plan_date, office_id, not_before=at
        )
    parent = await plans_repository.get_plan(session, plan.parent_plan_id)
    _, loaded = await replan_service.day_of_replan(
        session, parent, at or clock.now(), office_id=office_id
    )
    return loaded


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
    """Применяет решения по невлезшим заявкам.

    Перенос, отмена и «не дозвонились» только убирают работу из дня: маршруты от этого не
    меняются, поэтому день не пересчитываем — тот же черновик утверждается как есть. Согласие
    на предложенное время добавляет работу, и вот тогда идёт третий расчёт (docs/algoV2.md,
    шаг 5) с ярусами шага 3: кто влез в первый расчёт, того выкидывать нельзя.

    Решения и расчёт — одна транзакция: не получился расчёт — заявки не меняются.
    Прежний черновик остаётся в списке планов, новый ссылается на него.
    """
    draft = await reviewable_plan(session, plan_id, office_id=office_id)
    if not decisions:
        raise PlanDataError(["решений по заявкам нет — утвердите расчёт как есть"])
    waiting = {a.request_id for a in await planning_service.waiting_unassigned(session, draft)}
    stray = sorted({d.request_id for d in decisions} - waiting)
    if stray:
        raise PlanDataError(
            [
                f"заявка №{request_id} не среди невлезших в расчёт №{draft.id} — "
                "подберите окна ещё раз"
                for request_id in stray
            ]
        )

    solver = solver_of(draft, keep_baseline=True)
    objective_order = planning_service.objective_order_from_plan(draft) or DEFAULT_OBJECTIVE_ORDER
    # считаем заново только ради согласованного времени: без него в журнале не расчёт, а
    # применение решений оператора
    rebuilding = any(decision.action == "agree" for decision in decisions)
    async with run_log.track(
        "build" if rebuilding else "decisions",
        office_id=office_id,
        plan_date=draft.plan_date,
        solver=solver.value,
        user_id=user_id,
        run_id=run_id,
    ):
        placed_request_ids = {
            assignment.request_id
            for assignment in await plans_repository.list_plan_assignments(session, draft.id)
            if assignment.engineer_id is not None
        }
        async with run_log.step("Применяю решения оператора по заявкам", 2, 6):
            await run_log.note(
                f"решения по {run_log.plural(len(decisions), 'заявке', 'заявкам', 'заявкам')} "
                f"из расчёта №{draft.id}"
            )
            # решения проверяются по тому плану, за которым заявка числится: у черновика это
            # он сам, у пересчёта — пересчитываемый план, с которого заявку и снимают
            holder = draft
            if getattr(draft, "parent_plan_id", None) is not None:
                holder = await plans_repository.get_plan(session, draft.parent_plan_id) or draft
            await replan_service.apply_decisions(
                session,
                holder,
                decisions,
                office_id=office_id,
                user_id=user_id,
                occasion="при утверждении",
            )
        if rebuilding:
            # ярус B третьего расчёта: кто влез в первый (docs/algoV2.md, шаг 5). Переставить
            # их между бригадами и по времени решатель вправе, выкинуть — нет
            plan = await rebuild_with_decisions(
                session,
                draft,
                solver,
                objective_order,
                office_id=office_id,
                params=params,
                kept_request_ids=placed_request_ids,
            )
            plan.decisions_from_plan_id = draft.id
            plan.decisions_count = len(decisions)
        else:
            plan = await drop_decided(session, draft, decisions)
        await session.commit()
        await run_log.attach_plan(plan.id)
        return (await planning_service.summarize_plans(session, [plan]))[0]


async def rebuild_with_decisions(
    session: AsyncSession,
    draft: Plan,
    solver: SolverName,
    objective_order,
    *,
    office_id: int,
    params: SolverParams | None,
    kept_request_ids: set[int],
) -> Plan:
    """Третий расчёт круга: клиент согласился на время, и работы в дне прибавилось.

    Черновик дня считается заново целиком; пересчёт — снова от действующего плана и снова на
    выезд через запас. Прежний пересчёт в силу уже не вступит: его место занимает этот, иначе
    в свой момент сработали бы оба (docs/algoV2.md, шаги 5-6).
    """
    if getattr(draft, "parent_plan_id", None) is None:
        return await planning_service.build_inside_run(
            session,
            draft.plan_date,
            solver,
            objective_order,
            office_id=office_id,
            params=params,
            kept_request_ids=kept_request_ids,
        )
    parent, at = await replan_service.replannable(
        session, draft.parent_plan_id, None, office_id=office_id
    )
    plan = await replan_service.build_for_approval(
        session,
        parent,
        solver,
        objective_order,
        at,
        office_id=office_id,
        params=params,
        kept_request_ids=kept_request_ids,
    )
    draft.voided_at = clock.now()
    draft.void_reason = (
        f"Заменён пересчётом №{plan.id}: в нём учтены решения оператора по невлезшим заявкам"
    )
    return plan


async def drop_decided(session: AsyncSession, draft: Plan, decisions: list[ReplanDecision]) -> Plan:
    """Убирает из черновика заявки, которые перенесли или отменили. Расчёта нет.

    Работы стало меньше, маршруты бригад те же — пересчитывать нечего, и выпасть некому.
    В плане эти заявки больше не числятся даже как невлезшие: их день уже другой.
    """
    decided = {decision.request_id for decision in decisions}
    await run_log.note(
        f"Без пересчёта: из дня убрано "
        f"{run_log.plural(len(decided), 'заявка', 'заявки', 'заявок')}, "
        "маршруты бригад не меняются"
    )
    await plans_repository.delete_assignments(session, draft.id, decided)
    snapshot = draft.input_snapshot or {}
    order = [
        request_id for request_id in snapshot.get("request_order", []) if request_id not in decided
    ]
    draft.input_snapshot = {**snapshot, "request_order": order}
    await session.flush()
    return draft
