from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.references import references_repository
from src.schemas.references import ReferenceItem, ReferencesRead


async def get_references(session: AsyncSession) -> ReferencesRead:
    """Навыки, приоритеты и типы транспорта — для выпадающих списков у диспетчера."""
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    return ReferencesRead(
        skills=[ReferenceItem.model_validate(skill) for skill in skills],
        priorities=[ReferenceItem.model_validate(priority) for priority in priorities],
        transports=[ReferenceItem.model_validate(transport) for transport in transports],
    )
