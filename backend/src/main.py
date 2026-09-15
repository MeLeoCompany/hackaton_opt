from fastapi import FastAPI
from fastapi import Request as HttpRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1.router import router as v1_router
from src.core.config import settings
from src.services.requests.requests_service import (
    RequestDataError,
    RequestInUseError,
    RequestNotFoundError,
)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router, prefix="/api/v1")


@app.exception_handler(RequestNotFoundError)
async def handle_request_not_found(_: HttpRequest, error: RequestNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(RequestInUseError)
async def handle_request_in_use(_: HttpRequest, error: RequestInUseError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(RequestDataError)
async def handle_request_data_error(_: HttpRequest, error: RequestDataError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Проверьте данные заявок", "errors": error.messages},
    )
