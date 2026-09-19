"""Мобильное приложение бригады: её маршрут на день и отметки по заявкам.

Доступно только учётке бригады (require_brigade в src/api/v1/router.py).
"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_user
from src.db.session import get_db
from src.models import AppUser
from src.schemas.brigade import BrigadeDays, BrigadeFailure, BrigadeRoute
from src.services.brigade import brigade_service

router = APIRouter()


@router.get("/days", response_model=BrigadeDays, summary="Дни, на которые у бригады есть маршрут")
async def list_days(session: AsyncSession = Depends(get_db), user: AppUser = Depends(current_user)):
    return await brigade_service.route_days(session, user)


@router.get("/route", response_model=BrigadeRoute, summary="Маршрут бригады на день")
async def get_route(
    plan_date: date, session: AsyncSession = Depends(get_db), user: AppUser = Depends(current_user)
):
    return await brigade_service.get_route(session, user, plan_date)


@router.post(
    "/visits/{request_id}/depart", response_model=BrigadeRoute, summary="Выехали на заявку"
)
async def depart(
    request_id: int, session: AsyncSession = Depends(get_db), user: AppUser = Depends(current_user)
):
    return await brigade_service.mark(session, user, request_id, "depart")


@router.post("/visits/{request_id}/arrive", response_model=BrigadeRoute, summary="На месте")
async def arrive(
    request_id: int, session: AsyncSession = Depends(get_db), user: AppUser = Depends(current_user)
):
    return await brigade_service.mark(session, user, request_id, "arrive")


@router.post("/visits/{request_id}/done", response_model=BrigadeRoute, summary="Выполнено")
async def done(
    request_id: int, session: AsyncSession = Depends(get_db), user: AppUser = Depends(current_user)
):
    return await brigade_service.mark(session, user, request_id, "done")


@router.post("/visits/{request_id}/fail", response_model=BrigadeRoute, summary="Выполнить нельзя")
async def fail(
    request_id: int,
    payload: BrigadeFailure,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return await brigade_service.mark(session, user, request_id, "fail", payload.reason)
