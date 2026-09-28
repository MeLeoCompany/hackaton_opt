"""Какие заявки были в дне, когда начинался расчёт, и что в нём появилось нового.

И черновик дня, и пересчёт считаются не «прямо сейчас», а на точку «сейчас плюс запас на
расчёт и обзвон» (settings.replan_lead_minutes). Эти минуты бригады работают по действующему
плану: выезжают, приезжают, закрывают заявки. Такое движение расчёт и предполагал — мешать
утверждению оно не должно. А вот новые вводные — заявка, которой расчёт не видел, или
отмена — меняют день так, как расчёт не планировал: с ними он в силу не вступает
(docs/algoV2.md, шаги 1 и 6-9).

Список заявок снимается в начале расчёта (planning_service.build_inside_run, replan_service),
хранится в плане и сверяется при утверждении (planning_service.approve_plan, approve_replan).
То, что заявка досталась не той бригаде, видно там же по самим назначениям.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Plan, RequestStatusId
from src.repositories.requests import requests_repository
from src.services.planner import planner_loader


async def request_ids(session: AsyncSession, plan_date: date, office_id: int) -> list[int]:
    """Заявки дня офиса, которые расчёт раскладывает: «Новые» и «В плане»."""
    day = planner_loader.planning_day(plan_date)
    requests = await requests_repository.list_active_requests_in_period(
        session, day.day_start, day.day_end, plan_date=plan_date, office_id=office_id
    )
    return sorted(request.id for request in requests)


async def of_plan(session: AsyncSession, plan: Plan) -> list[int]:
    """То же по дню плана: и черновик, и пересчёт раскладывают заявки своего дня."""
    return await request_ids(session, plan.plan_date, plan.office_id)


async def new_since(
    session: AsyncSession, plan: Plan, before: list[int], current: list[int] | None = None
) -> list[str]:
    """Новые вводные с начала расчёта: чего в дне не было и что успели отменить.

    Заявка, которую бригада взяла в работу, из списка тоже уходит — это не новая вводная,
    а то самое движение по плану, ради которого и считали с запасом.

    current — уже прочитанные заявки дня: список планов сверяет по ним все черновики дня
    разом, чтобы не читать день заново на каждый.
    """
    now = current if current is not None else await of_plan(session, plan)
    appeared = sorted(set(now) - set(before))
    gone = await requests_repository.get_requests_by_ids(session, sorted(set(before) - set(now)))
    cancelled = sorted(
        request_id
        for request_id, request in gone.items()
        if request.status_id == RequestStatusId.CANCELLED
    )
    news = []
    if appeared:
        news.append(f"появились заявки {listed(appeared)}")
    if cancelled:
        news.append(f"отменили заявки {listed(cancelled)}")
    return news


# длинный перечень читать некому: причина уходит в подсказку и всплывающее сообщение
SHOWN = 5


def listed(request_ids: list[int]) -> str:
    shown = ", ".join(f"№{request_id}" for request_id in request_ids[:SHOWN])
    rest = len(request_ids) - SHOWN
    return f"{shown} и ещё {rest}" if rest > 0 else shown
