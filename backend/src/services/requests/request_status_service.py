"""Смена статуса заявки — только по таблице допустимых переходов.

Переход, которого нет в request_status_transition, запрещён. manual говорит, кто его
делает: оператор («В плане» -> «Выполнена») или система («Новая» -> «В плане» при
утверждении плана). Оператор не может сделать системный переход руками, а система —
ручной: иначе статусы разойдутся с планами.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError
from src.models import Request, RequestStatus, RequestStatusId
from src.repositories.request_statuses import request_statuses_repository


class StatusTransitionError(DataError):
    """Такой переход статуса запрещён."""


# заявка закрыта: бригада с ней закончила — выполнена или отменена
CLOSED_STATUSES = {RequestStatusId.DONE, RequestStatusId.CANCELLED}
# бригада заявку уже начала: едет к ней, работает на месте или закончила
STARTED_STATUSES = {RequestStatusId.EN_ROUTE, RequestStatusId.IN_PROGRESS, RequestStatusId.DONE}


async def change_status(
    session: AsyncSession,
    requests: list[Request],
    to_status_id: int,
    *,
    manual: bool,
    user_id: int | None = None,
    comment: str = "",
) -> None:
    """Переводит заявки в статус to_status_id и пишет это в историю.

    Если хоть одной переход запрещён — не меняется ни одна.
    """
    statuses = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    target = statuses.get(to_status_id)
    if target is None:
        raise StatusTransitionError([f"статуса №{to_status_id} нет в справочнике"])
    transitions = {
        (transition.from_status_id, transition.to_status_id): transition
        for transition in await request_statuses_repository.list_transitions(session)
    }

    problems = []
    for request in requests:
        if request.status_id == to_status_id:
            continue
        current = statuses[request.status_id].name
        transition = transitions.get((request.status_id, to_status_id))
        if transition is None:
            problems.append(
                f"заявка №{request.id}: из «{current}» в «{target.name}» перейти нельзя"
            )
        elif transition.manual != manual:
            problems.append(
                f"заявка №{request.id}: в «{target.name}» из «{current}» "
                + (
                    "переводит только оператор"
                    if transition.manual
                    else f"заявка переходит сама — {transition.description.lower()}"
                )
            )
    if problems:
        raise StatusTransitionError(problems)
    await check_route_chain(session, requests, to_status_id)

    for request in requests:
        if request.status_id == to_status_id:
            continue
        request_statuses_repository.add_history(
            session,
            [request.id],
            request.status_id,
            to_status_id,
            manual=manual,
            user_id=user_id,
            # заявка утверждённого плана — в истории видно, по какому плану она шла
            plan_id=request.approved_plan_id,
            comment=comment,
        )
        set_status(request, target)
        # «Новая» ждёт нового расчёта — за старым планом она больше не закреплена
        if to_status_id == RequestStatusId.NEW:
            request.approved_plan_id = None


def set_status(request: Request, status: RequestStatus) -> None:
    request.status_id = status.id
    request.status = status


async def require_transition(
    session: AsyncSession, from_status_id: int, to_status_id: int, *, manual: bool
) -> None:
    """Проверяет, что переход разрешён таблицей — перед массовым переводом одним UPDATE."""
    for transition in await request_statuses_repository.list_transitions(session):
        if (transition.from_status_id, transition.to_status_id) == (from_status_id, to_status_id):
            if transition.manual == manual:
                return
            break
    raise StatusTransitionError(
        [f"переход статуса №{from_status_id} -> №{to_status_id} не разрешён таблицей переходов"]
    )


async def check_route_chain(
    session: AsyncSession, requests: list[Request], to_status_id: int
) -> None:
    """В маршруте бригады утверждённого плана нет разрывов.

    Бригада идёт по визитам по порядку, поэтому «В работе» или «Выполнена» можно поставить
    заявке, только если все заявки перед ней в маршруте уже закрыты — выполнены или
    отменены (отменённая пропускается). Если меняют сразу несколько заявок маршрута,
    проверяется итоговое состояние: отметить выполненными первую и вторую вместе можно.
    """
    if to_status_id not in STARTED_STATUSES:
        return
    changing = {request.id for request in requests}
    problems = []
    for route in await request_statuses_repository.list_routes_of(session, requests):
        blocking: tuple[int, Request] | None = None  # первый ещё не закрытый визит маршрута
        for visit_number, request in enumerate(route, start=1):
            status_id = to_status_id if request.id in changing else request.status_id
            if request.id in changing and blocking is not None:
                earlier_number, earlier = blocking
                problems.append(
                    f"заявка №{request.id}: сначала закройте заявку №{earlier.id} — она раньше в "
                    f"маршруте бригады (визит {earlier_number}) и ещё не выполнена"
                )
            if status_id not in CLOSED_STATUSES and blocking is None:
                blocking = (visit_number, request)
    if problems:
        raise StatusTransitionError(problems)
