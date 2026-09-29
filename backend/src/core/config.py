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
    # Не больше числа процессов R5: лишние запросы только копятся в очереди и занимают память.
    r5_client_concurrency: int = Field(default=1, ge=1, le=16)
    # Короткое плечо пешком: общественный транспорт на нём всё равно не выигрывает, а вызов
    # R5 стоит секунды. На данных стенда (611 плеч) при пороге 12 минут отсекается четверть
    # всех вызовов, и лишь у 19 плеч из 276 «транспортных» пеший путь оказался короче порога —
    # там проигрыш в среднем 0.1 минуты, худший 0.8. Ноль отключает отсечение
    r5_skip_when_walk_minutes: float = Field(default=12.0, ge=0.0, le=120.0)
    # кеш ответов R5 в базе (docs/algoCachV1.md); в тестах без базы выключается
    travel_cache_enabled: bool = True
    # сколько дней хранится ответ R5; чистка идёт раз в сутки
    travel_cache_days: int = Field(default=7, ge=1, le=90)
    walking_speed_kmh: float = Field(default=4.8, ge=0.5, le=25, allow_inf_nan=False)
    # подпись токенов входа; в любом общем окружении задайте свой AUTH_SECRET
    auth_secret: str = "dev-secret-change-me"
    # пароль администратора: ставится при старте, в базе и миграциях не хранится.
    # Пусто — учётке дадут «admin», о чём приложение напишет в журнал
    admin_password: str = "admin"
    auth_token_hours: int = Field(default=12, gt=0)
    # ширина обещанного клиенту окна: предложенное время плюс допуск (docs/algoV2.md)
    promise_tolerance_minutes: int = Field(default=30, ge=5, le=240)
    # запас на сам расчёт и обзвон клиентов: пересчёт считается не «прямо сейчас», а с этого
    # момента вперёд, иначе к утверждению его маршруты уже начинаются в прошлом
    replan_lead_minutes: int = Field(default=15, ge=0, le=120)
    # техническая отсрочка: фоновая проверка ходит раз в несколько секунд, и между ней и
    # точкой выезда проходит время. Позже пересчёт в силу не вступает — считать заново
    replan_grace_minutes: int = Field(default=1, ge=0, le=120)
    # бригада выбилась из плана, если не выехала через столько минут после планового выезда
    departure_grace_minutes: int = Field(default=10, ge=0, le=120)
    # застрявшая бригада уже переработала норматив: считаем, что раньше чем через столько
    # минут она не освободится. Иначе пересчёт ставит ей выезд «прямо сейчас», она снова не
    # успевает, и день крутится в пересчётах (docs/algoV2.md, шаг 10)
    stuck_free_at_minutes: int = Field(default=30, ge=5, le=240)
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
