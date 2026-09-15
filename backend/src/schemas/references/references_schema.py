from pydantic import BaseModel, ConfigDict


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ReferencesRead(BaseModel):
    """Все справочники, из которых диспетчер выбирает значения заявки."""

    skills: list[ReferenceItem]
    priorities: list[ReferenceItem]
    transports: list[ReferenceItem]
