"""HTTP-эндпоинты планов.

Ошибки сервиса превращаются в ответы обработчиками в src/main.py:
нет данных на день — 422, план не найден — 404, Valhalla или cuOpt недоступны — 503.
"""

from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id, current_user
from src.db.session import get_db
from src.models import AppUser
from src.schemas.plans import (
    PlanApprovalReviewRequest,
    PlanBuildRequest,
    PlanDayCheck,
    PlanDetail,
    PlanningDayOption,
    PlanReplanRequest,
    PlanSummary,
    PlanSyncReport,
    PlanSyncRequest,
    ReplanPreview,
)
from src.services.planner import approval_review, plan_sync, planning_service, replan_service
from src.services.system import system_service

router = APIRouter()


@router.get(
    "/days", response_model=list[PlanningDayOption], summary="Дни, на которые есть активные заявки"
)
async def list_planning_days(
    session: AsyncSession = Depends(get_db), office_id: int = Depends(current_office_id)
):
    return await planning_service.list_planning_days(session, office_id=office_id)


@router.get("", response_model=list[PlanSummary], summary="Планы, новые первыми")
async def list_plans(
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await planning_service.list_plans(session, plan_date, office_id=office_id)


@router.post(
    "",
    response_model=PlanSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Построить план на день выбранным решателем",
)
async def build_plan(
    payload: PlanBuildRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await planning_service.build_plan_for_day(
        session,
        payload.plan_date,
        payload.solver,
        payload.objective_order,
        office_id=office_id,
        run_id=payload.run_id,
        user_id=user.id,
        params=payload.solver_params or await system_service.read_solver_params(session),
    )


@router.get(
    "/day-check",
    response_model=PlanDayCheck,
    summary="Что ждёт расчёт дня: сколько заявок и какие заняты утверждённым планом другого дня",
)
async def check_planning_day(
    plan_date: date,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await planning_service.check_planning_day(session, plan_date, office_id=office_id)


@router.post(
    "/{plan_id}/replan",
    response_model=PlanSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Пересчитать утверждённый план с текущего момента",
)
async def replan(
    plan_id: int,
    payload: PlanReplanRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Выполненные и начатые заявки остаются за бригадами, бригады стартуют оттуда, где они
    сейчас; остальное раскладывается заново. Получается отдельный план — его утверждение
    заменяет пересчитанный."""
    return await replan_service.replan(
        session,
        plan_id,
        payload.solver,
        payload.objective_order,
        payload.at,
        office_id=office_id,
        decisions=payload.decisions,
        free_at=payload.free_at,
        user_id=user.id,
        run_id=payload.run_id,
        params=payload.solver_params or await system_service.read_solver_params(session),
    )


@router.post(
    "/{plan_id}/replan/preview",
    response_model=ReplanPreview,
    summary="Пробный пересчёт без сохранения: на какие заявки не успеваем",
)
async def preview_replan(
    plan_id: int,
    payload: PlanReplanRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Тот же расчёт, что и пересчёт, но ничего не сохраняется. По заявкам, на которые не
    успеваем, диспетчер решает до пересчёта: новое окно или отмена (decisions пересчёта)."""
    return await replan_service.preview_replan(
        session,
        plan_id,
        payload.solver,
        payload.objective_order,
        payload.at,
        office_id=office_id,
        free_at=payload.free_at,
        user_id=user.id,
        run_id=payload.run_id,
        params=payload.solver_params or await system_service.read_solver_params(session),
    )


@router.post(
    "/{plan_id}/visits/{request_id}/departure",
    response_model=PlanDetail,
    summary="Разрешить бригаде выезд, хотя она отстаёт",
)
async def allow_departure(
    plan_id: int,
    request_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
) -> PlanDetail:
    """Оператор созвонился с клиентом: тот согласен подождать, бригада едет как есть."""
    return await planning_service.allow_departure(
        session, plan_id, request_id, office_id=office_id, user_id=user.id
    )


@router.post("/{plan_id}/approval", response_model=PlanSummary, summary="Утвердить план дня")
async def approve_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Заявки утверждённого плана закрепляются за ним: другие дни их не берут."""
    return await planning_service.approve_plan(
        session, plan_id, office_id=office_id, user_id=user.id
    )


@router.post(
    "/{plan_id}/approval/preview",
    response_model=ReplanPreview,
    summary="Перед утверждением: что предложить клиентам заявок, не влезших в черновик",
)
async def preview_approval(
    plan_id: int,
    payload: PlanApprovalReviewRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Невлезшие заявки черновика; с suggest — второй расчёт с раскрытыми окнами.

    suggest=false — просто список, кому нужно решение: расчёта нет (docs/algoV2.md, шаги 2-3).
    """
    return await approval_review.preview_approval(
        session,
        plan_id,
        office_id=office_id,
        user_id=user.id,
        run_id=payload.run_id,
        params=payload.solver_params or await system_service.read_solver_params(session),
        suggest=payload.suggest,
    )


@router.post(
    "/{plan_id}/windows",
    response_model=ReplanPreview,
    status_code=status.HTTP_201_CREATED,
    summary="Подобрать окна невлезшим заявкам: второй расчёт с раскрытыми окнами",
)
async def pick_windows(
    plan_id: int,
    payload: PlanApprovalReviewRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Получается новый расчёт дня: в нём невлезшие стоят на предложенное клиенту время.

    Клиент согласился — заявка остаётся там же, отказался — её вычёркивают. Пересчитывать
    день ещё раз не нужно (docs/algoV2.md, шаги 2-5).
    """
    return await approval_review.pick_windows(
        session,
        plan_id,
        office_id=office_id,
        user_id=user.id,
        run_id=payload.run_id,
        params=payload.solver_params or await system_service.read_solver_params(session),
    )


@router.delete(
    "/{plan_id}/windows",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отказаться от подбора окон: убрать его расчёт и вернуть прежний",
)
async def drop_windows(
    plan_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Предложенные времена не годятся: расчёт подбора удаляется, прежний снова в игре."""
    await approval_review.drop_windows(session, plan_id, office_id=office_id)


@router.post(
    "/{plan_id}/approval/decisions",
    response_model=PlanSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Учесть решения по невлезшим заявкам",
)
async def decide_approval(
    plan_id: int,
    payload: PlanApprovalReviewRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """Перенос и отмена убирают заявки из того же черновика — расчёта нет.

    Согласие на предложенное время добавляет работу: день считается заново, и новый черновик
    смотрят и утверждают отдельно (docs/algoV2.md, шаг 5).
    """
    return await approval_review.decide_approval(
        session,
        plan_id,
        payload.decisions,
        office_id=office_id,
        user_id=user.id,
        run_id=payload.run_id,
        params=payload.solver_params or await system_service.read_solver_params(session),
    )


@router.delete("/{plan_id}/approval", response_model=PlanSummary, summary="Снять утверждение плана")
async def cancel_plan_approval(
    plan_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await planning_service.cancel_plan_approval(
        session, plan_id, office_id=office_id, user_id=user.id
    )


@router.get("/{plan_id}", response_model=PlanDetail, summary="План с маршрутами исполнителей")
async def get_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await planning_service.get_plan_detail(session, plan_id, office_id=office_id)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить план")
async def delete_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    await planning_service.delete_plan(session, plan_id, office_id=office_id)


@router.post(
    "/{plan_id}/sync",
    response_model=PlanSyncReport,
    summary="Привести выбранные маршруты к плану на текущее время (режим демонстрации)",
)
async def sync_plan(
    plan_id: int,
    payload: PlanSyncRequest,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
) -> PlanSyncReport:
    """Отладка: выбранные бригады «идут строго по плану» до текущего системного времени,
    остальные остаются как есть. Работает только в режиме демонстрации."""
    return await plan_sync.sync_plan(
        session, plan_id, payload.engineer_ids, office_id=office_id, user_id=user.id
    )
