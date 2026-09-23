"""Какие заявки были в дне, когда начинался расчёт пересчёта, и что в нём появилось нового.

Пересчёт считается не «прямо сейчас», а на точку «сейчас плюс запас на расчёт и обзвон»
(settings.replan_lead_minutes). Эти минуты бригады работают по действующему плану: выезжают,
приезжают, закрывают заявки. Такое движение пересчёт и предполагал — мешать утверждению оно не
должно. А вот новые вводные — заявка, которой расчёт не видел, или отмена — меняют день так,
как пересчёт не планировал: с ними он в силу не вступает (docs/algoV2.md, шаги 7-9).

Список заявок снимается в начале расчёта (replan_service), хранится в плане и сверяется при
утверждении (planning_service.approve_replan). То, что заявка досталась не той бригаде, видно
там же по самим назначениям.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Plan, RequestStatusId
from src.repositories.requests import requests_repository
from src.services.planner import planner_loader


async def of_plan(session: AsyncSession, parent: Plan) -> list[int]:
    """Заявки дня, которые расчёт раскладывает: «Новые» и «В плане»."""
    day = planner_loader.planning_day(parent.plan_date)
    requests = await requests_repository.list_active_requests_in_period(
        session, day.day_start, day.day_end, plan_date=parent.plan_date, office_id=parent.office_id
    )
    return sorted(request.id for request in requests)


async def new_since(session: AsyncSession, parent: Plan, before: list[int]) -> list[str]:
    """Новые вводные с начала расчёта: чего в дне не было и что успели отменить.

    Заявка, которую бригада взяла в работу, из списка тоже уходит — это не новая вводная,
    а то самое движение по плану, ради которого и считали с запасом.
    """
    now = await of_plan(session, parent)
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


def listed(request_ids: list[int]) -> str:
    return ", ".join(f"№{request_id}" for request_id in request_ids)
