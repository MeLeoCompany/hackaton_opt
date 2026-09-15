from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.references import ReferencesRead
from src.services.references import references_service

router = APIRouter()


@router.get("", response_model=ReferencesRead, summary="Навыки, приоритеты и типы транспорта")
async def get_references(session: AsyncSession = Depends(get_db)) -> ReferencesRead:
    return await references_service.get_references(session)
