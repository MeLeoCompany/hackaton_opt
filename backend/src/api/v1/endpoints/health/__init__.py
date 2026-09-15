from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.health import service
from src.api.v1.endpoints.health.schemas import DatabaseHealthStatus, HealthStatus
from src.db.session import get_db

router = APIRouter()


@router.get("/", response_model=HealthStatus)
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/db", response_model=DatabaseHealthStatus)
async def health_db(session: AsyncSession = Depends(get_db)) -> DatabaseHealthStatus:
    return await service.check_database(session)
