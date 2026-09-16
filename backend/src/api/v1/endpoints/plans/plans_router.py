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
    PlanComparison,
    PlanComparisonRequest,
    PlanComparisonSummary,
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
    summary="Построить план на день: cuOpt или baseline",
)
async def build_plan(payload: PlanBuildRequest, session: AsyncSession = Depends(get_db)):
    return await planning_service.build_plan_for_day(session, payload.plan_date, payload.solver)


@router.post("/compare", response_model=PlanComparisonSummary, status_code=201,
             summary="Построить baseline и cuOpt на одинаковых данных")
async def build_comparison(payload: PlanComparisonRequest, session: AsyncSession = Depends(get_db)):
    return await planning_service.build_comparison(session, payload.plan_date)


@router.get("/{plan_id}/comparison", response_model=PlanComparison)
async def get_comparison(plan_id: int, session: AsyncSession = Depends(get_db)):
    return await planning_service.get_comparison(session, plan_id)


@router.get("/{plan_id}", response_model=PlanDetail, summary="План с маршрутами исполнителей")
async def get_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    return await planning_service.get_plan_detail(session, plan_id)
