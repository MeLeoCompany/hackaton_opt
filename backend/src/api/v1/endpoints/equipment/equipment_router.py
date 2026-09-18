"""HTTP-эндпоинты справочника оборудования.

Смотреть справочник может любой, кто вошёл; править — только администратор.
Ошибки сервиса (не найден, неверные данные, требуется заявками) превращаются в ответы
404 / 422 / 409 обработчиками в src/main.py.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin
from src.db.session import get_db
from src.schemas.equipment import EquipmentRead, EquipmentWrite
from src.services.equipment import equipment_service

router = APIRouter()
admin_only = [Depends(require_admin)]


@router.get("", response_model=list[EquipmentRead], summary="Все типы оборудования")
async def list_equipment(session: AsyncSession = Depends(get_db)):
    return await equipment_service.list_equipment(session)


@router.post(
    "",
    response_model=EquipmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить тип оборудования",
    dependencies=admin_only,
)
async def create_equipment(payload: EquipmentWrite, session: AsyncSession = Depends(get_db)):
    return await equipment_service.create_equipment(session, payload)


@router.put(
    "/{equipment_id}",
    response_model=EquipmentRead,
    summary="Изменить тип оборудования",
    dependencies=admin_only,
)
async def update_equipment(
    equipment_id: int, payload: EquipmentWrite, session: AsyncSession = Depends(get_db)
):
    return await equipment_service.update_equipment(session, equipment_id, payload)


@router.delete(
    "/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить тип оборудования",
    dependencies=admin_only,
)
async def delete_equipment(equipment_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    await equipment_service.delete_equipment(session, equipment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
