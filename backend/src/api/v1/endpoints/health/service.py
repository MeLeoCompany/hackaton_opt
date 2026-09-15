from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.health import repository
from src.api.v1.endpoints.health.schemas import DatabaseHealthStatus


async def check_database(session: AsyncSession) -> DatabaseHealthStatus:
    is_alive = await repository.ping_database(session)
    return DatabaseHealthStatus(
        status="ok" if is_alive else "error",
        database="connected" if is_alive else "unreachable",
    )
