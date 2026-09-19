from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrigadeWrite(BaseModel):
    """Бригада, как её заполняет администратор или диспетчер офиса.

    Логин и пароль — вход бригады в мобильное приложение, как у пользователей. Пустой логин —
    у бригады нет входа в приложение. Пароль при правке: пусто — остаётся прежний.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    is_active: bool = True
    login: str | None = None
    password: str | None = None

    @model_validator(mode="after")
    def check_password(self) -> "BrigadeWrite":
        if self.login == "":
            self.login = None
        if self.password == "":
            self.password = None
        if self.password is not None and len(self.password) < 4:
            raise ValueError("пароль — не короче 4 символов")
        return self


class BrigadeRead(BaseModel):
    id: int
    office_id: int
    name: str
    is_active: bool
    login: str | None  # None — входа в мобильное приложение нет
    shift_count: int  # сколько смен (исполнителей на день) заведено — такую бригаду не удалить
