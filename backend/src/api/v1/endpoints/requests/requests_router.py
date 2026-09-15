"""HTTP-эндпоинты заявок для диспетчера.

Ошибки сервиса (заявка не найдена, неверные данные, заявка используется) превращаются
в ответы 404 / 422 / 409 обработчиками в src/main.py.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.requests import (
    RequestActivityReport,
    RequestActivityUpdate,
    RequestCreate,
    RequestImportReport,
    RequestRead,
    RequestWrite,
)
from src.services.requests import requests_csv, requests_service

MAX_CSV_BYTES = 5 * 1024 * 1024

router = APIRouter()


@router.get("", response_model=list[RequestRead], summary="Все заявки, ближайшие по окну — первыми")
async def list_requests(session: AsyncSession = Depends(get_db)):
    return await requests_service.list_requests(session)


@router.get("/csv-template", summary="Шаблон CSV для загрузки заявок")
async def download_csv_template() -> Response:
    return Response(
        # BOM в начале — чтобы Excel открыл кириллицу без кракозябр
        content=requests_csv.build_csv_template().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="requests_template.csv"'},
    )


@router.post("/import", response_model=RequestImportReport, summary="Загрузить заявки из CSV")
async def import_requests(file: UploadFile = File(...), session: AsyncSession = Depends(get_db)):
    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    return await requests_service.import_requests_csv(session, content)


@router.patch(
    "/active",
    response_model=RequestActivityReport,
    summary="Включить или выключить заявки для планирования",
)
async def set_requests_active(payload: RequestActivityUpdate, session: AsyncSession = Depends(get_db)):
    return await requests_service.set_requests_active(session, payload.request_ids, payload.is_active)


@router.get("/{request_id}", response_model=RequestRead, summary="Одна заявка")
async def get_request(request_id: int, session: AsyncSession = Depends(get_db)):
    return await requests_service.get_request(session, request_id)


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED, summary="Добавить заявку")
async def create_request(payload: RequestCreate, session: AsyncSession = Depends(get_db)):
    return await requests_service.create_request(session, payload)


@router.put("/{request_id}", response_model=RequestRead, summary="Изменить заявку")
async def update_request(request_id: int, payload: RequestWrite, session: AsyncSession = Depends(get_db)):
    return await requests_service.update_request(session, request_id, payload)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить заявку")
async def delete_request(request_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    await requests_service.delete_request(session, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
