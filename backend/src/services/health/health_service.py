from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.health import ping_database
from src.schemas.health import DatabaseHealthStatus


async def check_database(session: AsyncSession) -> DatabaseHealthStatus:
    is_alive = await ping_database(session)
    return DatabaseHealthStatus(
        status="ok" if is_alive else "error",
        database="connected" if is_alive else "unreachable",
    )
