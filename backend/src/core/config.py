from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Routing Planner API"
    database_url: str
    valhalla_url: str = "http://localhost:8002"
    r5_url: str = "http://localhost:8003"
    r5_timeout_seconds: float = Field(default=180.0, gt=0.0, allow_inf_nan=False)
    # подпись токенов входа; в любом общем окружении задайте свой AUTH_SECRET
    auth_secret: str = "dev-secret-change-me"
    auth_token_hours: int = Field(default=12, gt=0)
    # минимум времени поиска; для больших задач лимит растёт до cuopt_max_time_limit_seconds
    cuopt_time_limit_seconds: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    cuopt_max_time_limit_seconds: float = Field(default=120.0, gt=0.0, allow_inf_nan=False)
    # последний уровень целевой функции: насколько различия пробега влияют на выбор
    # между планами с одинаковыми срочными/обычными заявками и числом исполнителей
    cuopt_distance_weight: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # диспетчер вводит время по Москве; перехода на летнее время там нет, поэтому хватает сдвига
    local_utc_offset_hours: int = 3

    @model_validator(mode="after")
    def check_cuopt_limits(self) -> "Settings":
        if self.cuopt_max_time_limit_seconds < self.cuopt_time_limit_seconds:
            raise ValueError("CUOPT_MAX_TIME_LIMIT_SECONDS не может быть меньше базового лимита")
        return self


# Значение database_url приходит из окружения/.env; статический анализатор этого не видит.
settings = Settings()  # type: ignore[call-arg]
