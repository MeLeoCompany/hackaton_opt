"""HTTP-эндпоинты справочника офисов.

Смотреть справочник может любой, кто вошёл; править — только администратор.
Ошибки сервиса (не найден, неверные данные, у офиса есть данные) превращаются в ответы
404 / 422 / 409 обработчиками в src/main.py.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.db.session import get_db
from src.schemas.offices import OfficeRead, OfficeWrite
from src.services.offices import offices_service

router = APIRouter()
admin_only = [Depends(require_admin)]


@router.get("", response_model=list[OfficeRead], summary="Все офисы")
async def list_offices(session: AsyncSession = Depends(get_db)):
    return await offices_service.list_offices(session)


@router.post(
    "",
    response_model=OfficeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить офис",
    dependencies=admin_only,
)
async def create_office(payload: OfficeWrite, session: AsyncSession = Depends(get_db)):
    return await offices_service.create_office(session, payload)


@router.put(
    "/{office_id}", response_model=OfficeRead, summary="Изменить офис", dependencies=admin_only
)
async def update_office(
    office_id: int, payload: OfficeWrite, session: AsyncSession = Depends(get_db)
):
    return await offices_service.update_office(session, office_id, payload)


@router.delete(
    "/{office_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить офис",
    dependencies=admin_only,
)
async def delete_office(office_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    await offices_service.delete_office(session, office_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
