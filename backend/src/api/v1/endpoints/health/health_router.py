from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.health import DatabaseHealthStatus, HealthStatus
from src.services.health import check_database

router = APIRouter()


@router.get("/", response_model=HealthStatus)
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/db", response_model=DatabaseHealthStatus)
async def health_db(session: AsyncSession = Depends(get_db)) -> DatabaseHealthStatus:
    return await check_database(session)
