from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Routing Planner API"
    database_url: str
    valhalla_url: str = "http://localhost:8002"
    # сколько секунд cuOpt ищет решение; для ~100 заявок хватает с запасом
    cuopt_time_limit_seconds: float = 10.0
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # диспетчер вводит время по Москве; перехода на летнее время там нет, поэтому хватает сдвига
    local_utc_offset_hours: int = 3


# Значение database_url приходит из окружения/.env; статический анализатор этого не видит.
settings = Settings()  # type: ignore[call-arg]
