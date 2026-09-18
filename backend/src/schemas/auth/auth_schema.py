from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CurrentUser(BaseModel):
    """Кто вошёл: интерфейс по этому решает, что показывать."""

    id: int
    login: str
    name: str
    role: str
    # офис диспетчера; у администратора пусто — он выбирает офис сам
    office_id: int | None
    office_name: str | None


class LoginResponse(BaseModel):
    token: str
    user: CurrentUser
