"""HTTP-эндпоинты заявок для диспетчера.

Ошибки сервиса (заявка не найдена, неверные данные, заявка используется) превращаются
в ответы 404 / 422 / 409 обработчиками в src/main.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id, current_user
from src.db.session import get_db
from src.models import AppUser
from src.schemas.requests import (
    RequestActivityReport,
    RequestActivityUpdate,
    RequestCreate,
    RequestImportReport,
    RequestRead,
    RequestStatusHistoryItem,
    RequestStatusUpdate,
    RequestWrite,
)
from src.services.requests import requests_csv, requests_service

MAX_CSV_BYTES = 5 * 1024 * 1024

router = APIRouter()


@router.get("", response_model=list[RequestRead], summary="Все заявки, ближайшие по окну — первыми")
async def list_requests(
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await requests_service.list_requests(session, office_id, plan_date)


@router.get("/csv-template", summary="Шаблон CSV для загрузки заявок")
async def download_csv_template() -> Response:
    return Response(
        # BOM в начале — чтобы Excel открыл кириллицу без кракозябр
        content=requests_csv.build_csv_template().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="requests_template.csv"'},
    )


@router.get("/export", summary="Выгрузить заявки дня в CSV")
async def export_requests(
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
) -> Response:
    content = await requests_service.export_requests_csv(session, office_id, plan_date)
    name = f"requests_{plan_date:%Y-%m-%d}.csv" if plan_date else "requests_all.csv"
    return Response(
        # BOM в начале — чтобы Excel открыл кириллицу без кракозябр
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/import", response_model=RequestImportReport, summary="Загрузить заявки из CSV")
async def import_requests(
    file: UploadFile = File(...),
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    """plan_date — перенести файл в этот день копией: время суток то же, номера новые."""
    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    return await requests_service.import_requests_csv(
        session, content, office_id, plan_date, user_id=user.id
    )


@router.patch(
    "/active",
    response_model=RequestActivityReport,
    summary="Включить или выключить заявки для планирования",
)
async def set_requests_active(
    payload: RequestActivityUpdate,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await requests_service.set_requests_active(
        session, payload.request_ids, payload.is_active, office_id, user.id
    )


@router.patch(
    "/status",
    response_model=RequestActivityReport,
    summary="Перевести заявки в статус (только ручные переходы из таблицы переходов)",
)
async def set_requests_status(
    payload: RequestStatusUpdate,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await requests_service.set_requests_status(
        session, payload.request_ids, payload.status_id, office_id, user.id
    )


@router.get(
    "/{request_id}/history",
    response_model=list[RequestStatusHistoryItem],
    summary="История статусов заявки: кто, когда и как их менял",
)
async def get_request_history(
    request_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await requests_service.get_request_history(session, request_id, office_id)


@router.get("/{request_id}", response_model=RequestRead, summary="Одна заявка")
async def get_request(
    request_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await requests_service.get_request(session, request_id, office_id)


@router.post(
    "", response_model=RequestRead, status_code=status.HTTP_201_CREATED, summary="Добавить заявку"
)
async def create_request(
    payload: RequestCreate,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await requests_service.create_request(session, payload, office_id, user.id)


@router.put("/{request_id}", response_model=RequestRead, summary="Изменить заявку (только «Новую»)")
async def update_request(
    request_id: int,
    payload: RequestWrite,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await requests_service.update_request(session, request_id, payload, office_id)


@router.post(
    "/{request_id}/duplicate",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Копия отменённой заявки — новая заявка с теми же данными",
)
async def duplicate_request(
    request_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
    user: AppUser = Depends(current_user),
):
    return await requests_service.duplicate_request(session, request_id, office_id, user.id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить заявку")
async def delete_request(
    request_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
) -> Response:
    await requests_service.delete_request(session, request_id, office_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
