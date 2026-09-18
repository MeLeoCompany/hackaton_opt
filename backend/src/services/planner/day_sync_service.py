"""Синхронизация дня с временем: статусы заявок приводятся к утверждённому плану.

На время T (текущее или заданное оператором) по плану видно, что с какой заявкой:
- работы по заявке закончились (начало работ + длительность ≤ T) — «Выполнена»;
- бригада к ней уже выехала — «В работе». Выезд — начало работ минус норматив дороги типа
  работ (справочник нормативов), но не раньше конца прошлой заявки маршрута (для первой —
  начала смены): если бригада пришла раньше окна, она ждёт на месте прошлой работы;
- «Новая» заявка дня вне плана, у которой окно уже закончилось, — «Отменена»: выполнить её
  в срок уже нельзя (об этом оператора предупреждаем отдельно).
Выполненные и отменённые заявки не трогаются, снятые с плана — тоже.

Сначала оператор смотрит предпросмотр — те же переходы с теми же проверками (таблица
переходов, разрывы в маршруте), только без сохранения. Время синхронизации запоминается на день
и офис; назад его не откатывают: статусы уже сменились.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError
from src.core.local_day import local_timezone
from src.models import Request, RequestStatusId
from src.repositories.plans import plans_repository
from src.repositories.references import references_repository
from src.repositories.requests import requests_repository
from src.schemas.plans import DaySyncReport, DaySyncState, DaySyncTransition
from src.services.planner import planner_loader
from src.services.requests import request_status_service

# в каком порядке переводятся группы: сначала закрываем, потом отправляем в работу —
# так следующая заявка маршрута уходит в работу, когда прошлая уже выполнена
APPLY_ORDER = (RequestStatusId.DONE, RequestStatusId.IN_PROGRESS, RequestStatusId.CANCELLED)


class DaySyncError(DataError):
    """Синхронизировать нельзя: время раньше прошлой синхронизации или переходы не проходят."""


@dataclass
class PlannedTransition:
    request: Request
    to_status_id: int
    reason: str
    warning: bool = False


def hhmm(moment: datetime) -> str:
    return moment.astimezone(local_timezone()).strftime("%H:%M")


async def get_day_sync_state(
    session: AsyncSession, plan_date: date, *, office_id: int
) -> DaySyncState:
    state = await plans_repository.get_day_sync(session, plan_date, office_id=office_id)
    if state is None:
        return DaySyncState(plan_date=plan_date)
    day_sync, user_name = state
    return DaySyncState(
        plan_date=plan_date,
        synced_to=day_sync.synced_to,
        synced_at=day_sync.synced_at,
        user_name=user_name,
    )


async def sync_day(
    session: AsyncSession,
    plan_date: date,
    sync_time: datetime,
    *,
    office_id: int,
    user_id: int | None,
    apply: bool,
) -> DaySyncReport:
    """Переходы синхронизации дня на sync_time. apply=False — предпросмотр: всё проверяется
    так же, но ничего не сохраняется."""
    state = await plans_repository.get_day_sync(session, plan_date, office_id=office_id)
    last_synced_to = state[0].synced_to if state else None
    if last_synced_to is not None and sync_time < last_synced_to:
        raise DaySyncError(
            [
                f"день уже синхронизирован на {hhmm(last_synced_to)} — назад время не откатывается, "
                "выберите это время или позже"
            ]
        )

    approved = await plans_repository.get_approved_plan(session, plan_date, office_id=office_id)
    planned = []
    if approved is not None:
        planned += await plan_transitions(session, approved.id, sync_time, office_id=office_id)
    planned += await expired_new_requests(session, plan_date, sync_time, office_id=office_id)

    report = DaySyncReport(
        plan_date=plan_date,
        sync_time=sync_time,
        approved_plan_id=approved.id if approved else None,
        last_synced_to=last_synced_to,
        transitions=[
            DaySyncTransition(
                request_id=item.request.id,
                address=item.request.address,
                from_status_id=item.request.status_id,
                to_status_id=item.to_status_id,
                reason=item.reason,
                warning=item.warning,
            )
            for item in planned
        ],
    )

    try:
        await apply_transitions(session, planned, sync_time, user_id=user_id)
    except DataError as error:
        report.problems = error.messages

    if not apply:
        await session.rollback()
        return report
    if report.problems:
        await session.rollback()
        raise DaySyncError(report.problems)
    await plans_repository.save_day_sync(
        session, plan_date, sync_time, office_id=office_id, user_id=user_id
    )
    await session.commit()
    report.applied = True
    return report


async def plan_transitions(
    session: AsyncSession, plan_id: int, sync_time: datetime, *, office_id: int
) -> list[PlannedTransition]:
    """Заявки утверждённого плана, которые к sync_time по плану выполнены или уже в работе."""
    routes = defaultdict(list)
    for assignment in await plans_repository.list_plan_assignments(session, plan_id):
        if assignment.engineer is not None and assignment.planned_arrival_time is not None:
            routes[assignment.engineer_id].append(assignment)

    # норматив дороги по типу работ: по нему считаем, когда бригада выезжает на заявку
    travel_minutes = {
        work_type.id: work_type.travel_minutes
        for work_type in await references_repository.list_work_types(session)
    }

    result = []
    for assignments in routes.values():
        assignments.sort(key=lambda assignment: assignment.visit_order or 0)
        engineer = assignments[0].engineer
        # раньше какого момента бригада выехать не может: на первую — начало смены, дальше —
        # конец прошлой работы
        free_at = engineer.shift_start
        for assignment in assignments:
            request = assignment.request
            work_start = assignment.planned_arrival_time
            work_end = work_start + timedelta(minutes=request.duration_minutes)
            road = timedelta(minutes=travel_minutes.get(request.work_type_id, 0))
            departure = max(free_at, work_start - road)
            free_at = work_end

            # снятые с плана, закрытые и чужого офиса не трогаем
            if request.approved_plan_id != plan_id or request.office_id != office_id:
                continue
            if request.status_id not in (RequestStatusId.PLANNED, RequestStatusId.IN_PROGRESS):
                continue
            if sync_time >= work_end:
                reason = f"по плану работы {hhmm(work_start)}–{hhmm(work_end)} закончились"
                result.append(PlannedTransition(request, RequestStatusId.DONE, reason))
            elif sync_time >= departure and request.status_id == RequestStatusId.PLANNED:
                reason = (
                    f"работы с {hhmm(work_start)}, {engineer.name} выехала в {hhmm(departure)} "
                    f"(дорога по нормативу {road.seconds // 60} мин)"
                )
                result.append(PlannedTransition(request, RequestStatusId.IN_PROGRESS, reason))
    return result


async def expired_new_requests(
    session: AsyncSession, plan_date: date, sync_time: datetime, *, office_id: int
) -> list[PlannedTransition]:
    """«Новые» заявки дня вне плана, окно которых к sync_time закончилось."""
    day = planner_loader.planning_day(plan_date)
    requests = await requests_repository.list_active_requests_in_period(
        session, day.day_start, day.day_end, plan_date=plan_date, office_id=office_id
    )
    return [
        PlannedTransition(
            request,
            RequestStatusId.CANCELLED,
            f"окно {hhmm(request.window_start)}–{hhmm(request.window_end)} закончилось, "
            "а в плане заявки нет — выполнить её в срок уже нельзя",
            warning=True,
        )
        for request in requests
        if request.status_id == RequestStatusId.NEW
        and request.approved_plan_id is None
        and request.window_end <= sync_time
    ]


async def apply_transitions(
    session: AsyncSession,
    planned: list[PlannedTransition],
    sync_time: datetime,
    *,
    user_id: int | None,
) -> None:
    comment = f"Синхронизация с планом на {sync_time.astimezone(local_timezone()):%d.%m %H:%M}"
    for to_status_id in APPLY_ORDER:
        group = [item.request for item in planned if item.to_status_id == to_status_id]
        if group:
            await request_status_service.change_status(
                session, group, to_status_id, manual=True, user_id=user_id, comment=comment
            )
    await session.flush()
