from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id, require_admin
from src.db.session import get_db
from src.schemas.references import ReferencesRead, WorkTypeItem, WorkTypeNormsWrite
from src.services.references import references_service

router = APIRouter()


@router.get("", response_model=ReferencesRead, summary="Все справочники: навыки, приоритеты, транспорт, типы работ, офисы, оборудование")
async def get_references(
    session: AsyncSession = Depends(get_db), office_id: int = Depends(current_office_id)
) -> ReferencesRead:
    return await references_service.get_references(session, office_id)


@router.put(
    "/work-types/{work_type_id}",
    response_model=WorkTypeItem,
    summary="Изменить нормативы типа работ (только администратор)",
    dependencies=[Depends(require_admin)],
)
async def update_work_type_norms(
    work_type_id: int, payload: WorkTypeNormsWrite, session: AsyncSession = Depends(get_db)
) -> WorkTypeItem:
    """Меняет только подстановку по умолчанию: существующие заявки остаются как есть."""
    return await references_service.update_work_type_norms(session, work_type_id, payload)
