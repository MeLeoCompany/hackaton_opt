"""HTTP-эндпоинты планов.

Ошибки сервиса превращаются в ответы обработчиками в src/main.py:
нет данных на день — 422, план не найден — 404, Valhalla или cuOpt недоступны — 503.
"""

from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.plans import (
    PlanBuildRequest,
    PlanDayCheck,
    PlanDetail,
    PlanningDayOption,
    PlanSummary,
)
from src.services.planner import planning_service

router = APIRouter()


@router.get("/days", response_model=list[PlanningDayOption], summary="Дни, на которые есть активные заявки")
async def list_planning_days(session: AsyncSession = Depends(get_db)):
    return await planning_service.list_planning_days(session)


@router.get("", response_model=list[PlanSummary], summary="Планы, новые первыми")
async def list_plans(plan_date: date | None = None, session: AsyncSession = Depends(get_db)):
    return await planning_service.list_plans(session, plan_date)


@router.post(
    "",
    response_model=PlanSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Построить план на день выбранным решателем",
)
async def build_plan(payload: PlanBuildRequest, session: AsyncSession = Depends(get_db)):
    return await planning_service.build_plan_for_day(session, payload.plan_date, payload.solver)


@router.get(
    "/day-check",
    response_model=PlanDayCheck,
    summary="Что ждёт расчёт дня: сколько заявок и какие заняты утверждённым планом другого дня",
)
async def check_planning_day(plan_date: date, session: AsyncSession = Depends(get_db)):
    return await planning_service.check_planning_day(session, plan_date)


@router.post("/{plan_id}/approval", response_model=PlanSummary, summary="Утвердить план дня")
async def approve_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    """Заявки утверждённого плана закрепляются за ним: другие дни их не берут."""
    return await planning_service.approve_plan(session, plan_id)


@router.delete("/{plan_id}/approval", response_model=PlanSummary, summary="Снять утверждение плана")
async def cancel_plan_approval(plan_id: int, session: AsyncSession = Depends(get_db)):
    return await planning_service.cancel_plan_approval(session, plan_id)


@router.get("/{plan_id}", response_model=PlanDetail, summary="План с маршрутами исполнителей")
async def get_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    return await planning_service.get_plan_detail(session, plan_id)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить план")
async def delete_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    await planning_service.delete_plan(session, plan_id)
