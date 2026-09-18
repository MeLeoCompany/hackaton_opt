from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_office_id
from src.db.session import get_db
from src.schemas.references import ReferencesRead
from src.services.references import references_service

router = APIRouter()


@router.get("", response_model=ReferencesRead, summary="Все справочники: навыки, приоритеты, транспорт, типы работ, офисы, оборудование")
async def get_references(
    session: AsyncSession = Depends(get_db), office_id: int = Depends(current_office_id)
) -> ReferencesRead:
    return await references_service.get_references(session, office_id)
