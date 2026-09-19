from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserWrite(BaseModel):
    """Учётка, как её заполняет администратор."""

    model_config = ConfigDict(str_strip_whitespace=True)

    login: str = Field(min_length=1)
    name: str = Field(min_length=1)
    # учётки бригад заводятся в справочнике бригад (brigades), не здесь
    role: Literal["admin", "dispatcher"]
    office_id: int | None = Field(default=None, gt=0)
    is_active: bool = True
    # при создании обязателен; при изменении пусто — пароль остаётся прежним
    password: str | None = None

    @model_validator(mode="after")
    def dispatcher_needs_office(self) -> "UserWrite":
        if self.role == "dispatcher" and self.office_id is None:
            raise ValueError("диспетчеру нужен офис: без него он не увидит ни одной заявки")
        if self.password is not None and len(self.password) < 4:
            raise ValueError("пароль — не короче 4 символов")
        return self


class UserRead(BaseModel):
    id: int
    login: str
    name: str
    role: str
    office_id: int | None
    is_active: bool
