from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    # системное время могли перемотать для демонстрации — поднимаем сдвиг из базы
    async with async_session_maker() as session:
        await system_service.load_offset(session)
    yield


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
