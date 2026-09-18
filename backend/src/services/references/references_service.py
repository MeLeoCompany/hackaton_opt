from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.repositories.references import references_repository
from src.schemas.references import (
    EquipmentItem,
    OfficeItem,
    ReferenceItem,
    ReferencesRead,
    WorkTypeItem,
    WorkTypeNormsWrite,
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


class WorkTypeNotFoundError(NotFoundError):
    """Такого типа работ нет."""


async def update_work_type_norms(
    session: AsyncSession, work_type_id: int, payload: WorkTypeNormsWrite
) -> WorkTypeItem:
    """Меняет нормативы типа работ. Базовый норматив (дорога + работа) БД пересчитает сама.

    Существующие заявки не трогаются: длительность у каждой своя. Новый норматив
    подставится в новые заявки и в строки CSV без длительности.
    """
    work_type = await references_repository.get_work_type(session, work_type_id)
    if work_type is None:
        raise WorkTypeNotFoundError(f"Тип работ №{work_type_id} не найден")
    work_type.travel_minutes = payload.travel_minutes
    work_type.work_minutes = payload.work_minutes
    await session.commit()
    # baseline_minutes — вычисляемая колонка: забираем из БД новое значение
    await session.refresh(work_type)
    return WorkTypeItem.model_validate(work_type)
