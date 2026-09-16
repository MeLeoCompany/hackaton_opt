from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.references import references_repository
from src.schemas.references import ReferenceItem, ReferencesRead, WorkTypeItem


async def get_references(session: AsyncSession) -> ReferencesRead:
    """Навыки, приоритеты, транспорт и типы работ — для выпадающих списков у диспетчера."""
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    work_types = await references_repository.list_work_types(session)
    return ReferencesRead(
        skills=[ReferenceItem.model_validate(skill) for skill in skills],
        priorities=[ReferenceItem.model_validate(priority) for priority in priorities],
        transports=[ReferenceItem.model_validate(transport) for transport in transports],
        work_types=[WorkTypeItem.model_validate(work_type) for work_type in work_types],
    )
