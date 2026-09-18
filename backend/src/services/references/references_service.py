from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.references import references_repository
from src.schemas.references import (
    EquipmentItem,
    OfficeItem,
    ReferenceItem,
    ReferencesRead,
    WorkTypeItem,
)


async def get_references(session: AsyncSession, office_id: int) -> ReferencesRead:
    """Навыки, приоритеты, транспорт, типы работ, офисы и оборудование — для выпадающих списков."""
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    work_types = await references_repository.list_work_types(session)
    # в рабочих формах нужен только свой офис: чужие диспетчеру не видны
    offices = [
        office
        for office in await references_repository.list_offices(session)
        if office.id == office_id
    ]
    equipment = await references_repository.list_equipment(session)
    return ReferencesRead(
        skills=[ReferenceItem.model_validate(skill) for skill in skills],
        priorities=[ReferenceItem.model_validate(priority) for priority in priorities],
        transports=[ReferenceItem.model_validate(transport) for transport in transports],
        work_types=[WorkTypeItem.model_validate(work_type) for work_type in work_types],
        offices=[OfficeItem.model_validate(office) for office in offices],
        equipment=[EquipmentItem.model_validate(item) for item in equipment],
    )
