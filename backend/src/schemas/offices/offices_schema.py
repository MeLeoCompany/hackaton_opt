from pydantic import BaseModel, ConfigDict, Field


class OfficeWrite(BaseModel):
    """Поля офиса, которые диспетчер заполняет в справочнике."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class OfficeRead(OfficeWrite):
    id: int
    # сколько исполнителей выезжает из офиса: видно, кого заденет перенос или удаление
    engineer_count: int = 0
