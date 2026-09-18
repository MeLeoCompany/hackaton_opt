"""HTTP-эндпоинты исполнителей.

Ошибки сервиса (не найден, неверные данные, используется в плане) превращаются
в ответы 404 / 422 / 409 обработчиками в src/main.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id
from src.db.session import get_db
from src.schemas.engineers import (
    EngineerCreate,
    EngineerImportReport,
    EngineerRead,
    EngineerWrite,
)
from src.services.engineers import engineers_csv, engineers_service

MAX_CSV_BYTES = 5 * 1024 * 1024

router = APIRouter()


@router.get("", response_model=list[EngineerRead], summary="Все исполнители")
async def list_engineers(
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await engineers_service.list_engineers(session, office_id, plan_date)


@router.get("/csv-template", summary="Шаблон CSV для загрузки исполнителей")
async def download_csv_template() -> Response:
    return Response(
        # BOM в начале — чтобы Excel открыл кириллицу без кракозябр
        content=engineers_csv.build_csv_template().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="engineers_template.csv"'},
    )


@router.get("/export", summary="Выгрузить исполнителей дня в CSV")
async def export_engineers(
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
) -> Response:
    content = await engineers_service.export_engineers_csv(session, office_id, plan_date)
    name = f"engineers_{plan_date:%Y-%m-%d}.csv" if plan_date else "engineers_all.csv"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/import", response_model=EngineerImportReport, summary="Загрузить исполнителей из CSV"
)
async def import_engineers(
    file: UploadFile = File(...),
    plan_date: date | None = None,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    """plan_date — перенести смены в этот день копией: время суток то же, номера новые."""
    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    return await engineers_service.import_engineers_csv(session, content, office_id, plan_date)


@router.get("/{engineer_id}", response_model=EngineerRead, summary="Один исполнитель")
async def get_engineer(
    engineer_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await engineers_service.get_engineer(session, engineer_id, office_id)


@router.post(
    "",
    response_model=EngineerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить исполнителя",
)
async def create_engineer(
    payload: EngineerCreate,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await engineers_service.create_engineer(session, payload, office_id)


@router.put("/{engineer_id}", response_model=EngineerRead, summary="Изменить исполнителя")
async def update_engineer(
    engineer_id: int,
    payload: EngineerWrite,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
):
    return await engineers_service.update_engineer(session, engineer_id, payload, office_id)


@router.delete(
    "/{engineer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить исполнителя"
)
async def delete_engineer(
    engineer_id: int,
    session: AsyncSession = Depends(get_db),
    office_id: int = Depends(current_office_id),
) -> Response:
    await engineers_service.delete_engineer(session, engineer_id, office_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
