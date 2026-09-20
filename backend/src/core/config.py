from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Routing Planner API"
    database_url: str
    valhalla_url: str = "http://localhost:8002"
    r5_url: str = "http://localhost:8003"
    r5_gtfs_path: Path = Path("transit/generated/moscow-pilot.gtfs.zip")
    r5_timeout_seconds: float = Field(default=180.0, gt=0.0, allow_inf_nan=False)
    r5_matrix_block_origins: int = Field(default=5, ge=1, le=1000)
    r5_matrix_block_max_pairs: int = Field(default=500, ge=1, le=100_000)
    r5_matrix_single_max_points: int = Field(default=100, ge=2, le=1000)
    walking_speed_kmh: float = Field(default=4.8, ge=0.5, le=25, allow_inf_nan=False)
    # подпись токенов входа; в любом общем окружении задайте свой AUTH_SECRET
    auth_secret: str = "dev-secret-change-me"
    auth_token_hours: int = Field(default=12, gt=0)
    # минимум времени поиска; для больших задач лимит растёт до cuopt_max_time_limit_seconds
    cuopt_time_limit_seconds: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    cuopt_max_time_limit_seconds: float = Field(default=120.0, gt=0.0, allow_inf_nan=False)
    # последний уровень целевой функции: насколько различия пробега влияют на выбор
    # между планами с одинаковыми срочными/обычными заявками и числом исполнителей
    cuopt_distance_weight: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    # число попыток уточнить расписание ОТ после решения статической задачи
    transit_plan_max_attempts: int = Field(default=4, ge=1, le=10)
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
