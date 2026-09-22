import asyncio
import logging
from contextlib import asynccontextmanager

from asyncpg.exceptions import CannotConnectNowError
from fastapi import FastAPI
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from src.api.v1.router import router as v1_router
from src.core.config import settings
from src.core.errors import (
    CalculationCancelled,
    DataError,
    ExternalServiceError,
    InUseError,
    NotFoundError,
)
from src.db.session import async_session_maker
from src.services.system import system_service
from src.services.travel import travel_cache

# сколько ждать базу при старте: после перезапуска Docker все контейнеры поднимаются разом,
# и depends_on при этом не работает — бэкенд может проснуться раньше Postgres
DB_WAIT_SECONDS = 90
DB_RETRY_SECONDS = 2

logger = logging.getLogger("src.startup")
# база не принимает подключения: не запущена, стартует или восстанавливается
DB_NOT_READY = (OSError, CannotConnectNowError, OperationalError, InterfaceError)


async def load_offset_when_db_ready() -> None:
    """Системное время могли перемотать для демонстрации — поднимаем сдвиг из базы.

    База ещё не готова — ждём её, иначе приложение не стартует, а контейнер остаётся «живым»
    (перезагрузчик uvicorn работает) и никто его не перезапустит.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DB_WAIT_SECONDS
    while True:
        try:
            async with async_session_maker() as session:
                await system_service.load_offset(session)
            return
        except DB_NOT_READY as error:
            if loop.time() >= deadline:
                raise
            logger.warning("база ещё не готова (%s) — жду %s с", error, DB_RETRY_SECONDS)
            await asyncio.sleep(DB_RETRY_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await load_offset_when_db_ready()
    # кеш R5: раз в сутки удаляем старое и сверяем расписание GTFS (docs/algoCachV1.md)
    maintenance = asyncio.create_task(travel_cache.maintenance_loop())
    try:
        yield
    finally:
        maintenance.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router, prefix="/api/v1")


@app.exception_handler(NotFoundError)
async def handle_not_found(_: HttpRequest, error: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(InUseError)
async def handle_in_use(_: HttpRequest, error: InUseError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(CalculationCancelled)
async def handle_cancelled(_: HttpRequest, error: CalculationCancelled) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(DataError)
async def handle_data_error(_: HttpRequest, error: DataError) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"detail": "Проверьте данные", "errors": error.messages}
    )


@app.exception_handler(ExternalServiceError)
async def handle_external_service_error(
    _: HttpRequest, error: ExternalServiceError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})
