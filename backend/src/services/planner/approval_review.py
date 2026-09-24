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
from src.services.planner import planning_service, replan_service, run_log
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
    """По каким заявкам расчёта нужно решение оператора и что можно предложить клиенту.

    Ничего не считает: расчёт подбора окон (pick_windows) уже разложил день с раскрытыми
    окнами, и предложение клиенту — это время, на которое он сам поставил заявку. Остальным
    предлагать нечего: «сегодня никак», нужен перенос или отмена (docs/algoV2.md, шаги 3-4).
    """
    plan = await reviewable_plan(session, plan_id, office_id=office_id)
    unassigned = await planning_service.waiting_unassigned(session, plan)
    counts = await plans_repository.count_assignments_by_plan(session, [plan.id])
    _, assigned_count, _ = counts.get(plan.id, (0, 0, 0))
    tolerance = settings.promise_tolerance_minutes
    now = clock.now()
    return ReplanPreview(
        plan_id=plan.id,
        assigned_count=assigned_count,
        promise_tolerance_minutes=tolerance,
        unassigned=[
            *(offered(assignment, tolerance, now) for assignment in await offers(session, plan)),
            *(problem(assignment, None, tolerance, now) for assignment in unassigned),
        ],
    )


async def offers(session: AsyncSession, plan: Plan) -> list:
    """Заявки, которым этот расчёт подобрал окно и по которым ждут ответа клиента."""
    return await planning_service.undecided_offers(session, plan)


def offered(assignment, tolerance_minutes: int, now: datetime) -> ReplanProblem:
    """Предложение клиенту: расчёт поставил заявку на это время, его и называем."""
    request = assignment.request
    start = assignment.planned_arrival_time
    promised = request.promised_from
    reason = "в своё окно заявка сегодня не влезла — это время с раскрытым окном"
    if promised is not None:
        reason = (
            f"клиенту обещали {planning_service.local_clock(promised)}, но в это время бригада "
            "уже не успевает — договоритесь заново"
        )
    return ReplanProblem(
        request_id=assignment.request_id,
        address=request.address,
        window_start=request.window_start,
        window_end=request.window_end,
        status_id=request.status_id,
        reason=reason,
        expired=request.window_end < now,
        suggested_start=start,
        suggested_end=start + timedelta(minutes=tolerance_minutes),
        suggested_engineer=assignment.engineer.name if assignment.engineer else None,
    )


async def pick_windows(
    session: AsyncSession,
    plan_id: int,
    *,
    office_id: int,
    user_id: int | None = None,
    run_id: UUID | None = None,
    params: SolverParams | None = None,
) -> ReplanPreview:
    """Второй расчёт круга: невлезшим раскрываем окно и раскладываем день заново.

    Получается новый расчёт дня — его и утверждают. Клиент согласился на предложенное время —
    заявка остаётся ровно там, куда её поставил этот расчёт; отказался — её вычёркивают.
    Считать день ещё раз не нужно, и выпадать из него некому (docs/algoV2.md, шаги 2-5).

    Для расчёта базовым алгоритмом считает cuOpt: базовый не умеет ярусы, а без них раскрытая
    заявка вытеснит ту, что уже влезла.
    """
    # это и есть расчёт подбора, по которому ещё ждут ответов: показываем его предложения
    picked_self = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if await planning_service.undecided_offers(session, picked_self):
        return await preview_approval(session, plan_id, office_id=office_id)
    # окна этому расчёту уже подбирали: возвращаем те же предложения, а не считаем снова.
    # Смотрим до проверок самого расчёта: подбор окон мог его уже сменить, и тогда решать
    # нужно по тому, что получилось, а не отказывать оператору
    picked = await plans_repository.windows_plan_of(session, plan_id)
    if picked is not None:
        return await preview_approval(session, picked.id, office_id=office_id)
    source = await reviewable_plan(session, plan_id, office_id=office_id)
    unassigned = await planning_service.waiting_unassigned(session, source)
    if not unassigned:
        raise PlanDataError(
            [f"в расчёт №{source.id} вошли все заявки — подбирать окна не для кого"]
        )
    solver = solver_of(source)
    objective_order = planning_service.objective_order_from_plan(source) or DEFAULT_OBJECTIVE_ORDER
    widened = {assignment.request_id for assignment in unassigned}
    async with run_log.track(
        "windows",
        office_id=office_id,
        plan_date=source.plan_date,
        solver=solver.value,
        user_id=user_id,
        run_id=run_id,
    ):
        await run_log.note(
            f"раскрываю окно у {run_log.plural(len(widened), 'заявки', 'заявок', 'заявок')}, "
            f"не вошедших в расчёт №{source.id}"
        )
        if getattr(source, "parent_plan_id", None) is None:
            plan = await planning_service.build_inside_run(
                session,
                source.plan_date,
                solver,
                objective_order,
                office_id=office_id,
                params=params,
                widen_request_ids=widened,
            )
        else:
            parent, at = await replan_service.replannable(
                session, source.parent_plan_id, None, office_id=office_id
            )
            plan = await replan_service.build_for_approval(
                session,
                parent,
                solver,
                objective_order,
                at,
                office_id=office_id,
                params=params,
                widen_request_ids=widened,
            )
        plan.decisions_from_plan_id = source.id
        await session.commit()
        await run_log.attach_plan(plan.id)
    return await preview_approval(session, plan.id, office_id=office_id)


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
    """Применяет решения оператора по заявкам расчёта. Расчёта здесь нет вовсе.

    Согласие на подобранное окно ничего не двигает: заявка остаётся там, куда её поставил
    подбор окон, а её окно в базе сужается до обещанного. Перенос, отмена и «не дозвонились»
    только убирают работу из дня — маршруты от этого не меняются, и выпасть некому. Поэтому
    день не пересчитывается: утверждается ровно тот расклад, который видел оператор
    (docs/algoV2.md, шаги 4-5).

    Решения и правка плана — одна транзакция: не вышло — заявки не меняются.
    """
    draft = await reviewable_plan(session, plan_id, office_id=office_id)
    if not decisions:
        raise PlanDataError(["решений по заявкам нет — утвердите расчёт как есть"])
    # решать можно о том, кто в расчёт не вошёл, и о том, кому он подобрал окно
    waiting = {a.request_id for a in await planning_service.waiting_unassigned(session, draft)}
    waiting |= {a.request_id for a in await offers(session, draft)}
    stray = sorted({d.request_id for d in decisions} - waiting)
    if stray:
        raise PlanDataError(
            [
                f"заявка №{request_id} не ждёт решения в расчёте №{draft.id} — "
                "откройте его ещё раз"
                for request_id in stray
            ]
        )

    async with run_log.track(
        "decisions",
        office_id=office_id,
        plan_date=draft.plan_date,
        solver=solver_of(draft, keep_baseline=True).value,
        user_id=user_id,
        run_id=run_id,
    ):
        async with run_log.step("Применяю решения оператора по заявкам", 2, 90):
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
            # согласованные остаются в расчёте как есть, остальных из него вычёркиваем
            dropped = [decision for decision in decisions if decision.action != "agree"]
            plan = await drop_decided(session, draft, dropped)
            plan.decisions_count = (plan.decisions_count or 0) + len(decisions)
        await session.commit()
        await run_log.attach_plan(plan.id)
        return (await planning_service.summarize_plans(session, [plan]))[0]


async def drop_windows(session: AsyncSession, plan_id: int, *, office_id: int) -> None:
    """Оператор отказался от подбора окон: расчёт убираем, прежний возвращаем в игру.

    Подбор окон сохраняет свой расклад сразу, и прежний пересчёт при этом отзывается. Если
    оператор решил, что предложенные времена не годятся, откатываем и то, и другое — иначе
    отказаться было бы невозможно (docs/algoV2.md, шаги 3-4).
    """
    plan = await planning_service.find_plan(session, plan_id, office_id=office_id)
    if not (getattr(plan, "input_snapshot", None) or {}).get("widened_requests"):
        raise PlanInUseError(f"Расчёт №{plan_id} получен не подбором окон — отказываться нечем")
    if plan.approved_at is not None or plan.decisions_count:
        raise PlanInUseError(
            f"По расчёту №{plan_id} решения уже приняты — откажитесь от него удалением плана"
        )
    await planning_service.revive_source_of(session, plan)
    await plans_repository.delete_plan(session, plan)
    await session.commit()


async def drop_decided(session: AsyncSession, draft: Plan, decisions: list[ReplanDecision]) -> Plan:
    """Убирает из расчёта заявки, которые перенесли или отменили. Расчёта нет.

    Работы стало меньше, маршруты бригад те же — пересчитывать нечего, и выпасть некому.
    Маршрут просто идёт мимо убранной заявки. В плане она больше не числится даже как
    невлезшая: её день уже другой.
    """
    decided = {decision.request_id for decision in decisions}
    if not decided:
        return draft
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
