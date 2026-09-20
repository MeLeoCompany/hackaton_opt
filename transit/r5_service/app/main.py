from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from .config import Settings
from .models import (
    HealthResponse,
    MatrixBlockRequest,
    MatrixBlockResponse,
    MatrixRequest,
    MatrixResponse,
    RouteRequest,
    RouteResponse,
)
from .routing import route, travel_time_matrix, travel_time_matrix_block


def _wait_for_file(path: Path, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while not path.is_file() or path.stat().st_size == 0:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"файл данных не появился за {timeout} с: {path}")
        time.sleep(2)


def _load_network(settings: Settings):
    _wait_for_file(settings.osm_path, settings.source_wait_seconds)
    _wait_for_file(settings.gtfs_path, settings.source_wait_seconds)
    import r5py

    return r5py.TransportNetwork(
        str(settings.osm_path),
        [str(settings.gtfs_path)],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    app.state.settings = settings
    app.state.network = None
    app.state.load_error = None
    app.state.routing_lock = asyncio.Lock()
    try:
        app.state.network = await asyncio.to_thread(_load_network, settings)
    # Во время загрузки R5 библиотека JPype может вернуть разные исключения
    # как со стороны Java, так и со стороны Python.
    except Exception as error:  # noqa: BLE001
        app.state.load_error = str(error)
    yield


app = FastAPI(
    title="Маршрутизатор общественного транспорта R5",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    if request.app.state.network is not None:
        return HealthResponse(status="ok", network_loaded=True)
    raise HTTPException(
        status_code=503,
        detail=HealthResponse(
            status="error",
            network_loaded=False,
            error=request.app.state.load_error,
        ).model_dump(),
    )


@app.post("/route", response_model=RouteResponse)
async def public_transport_route(
    payload: RouteRequest, request: Request
) -> RouteResponse:
    network = request.app.state.network
    if network is None:
        raise HTTPException(status_code=503, detail="транспортный граф R5 не загружен")
    try:
        async with request.app.state.routing_lock:
            return await asyncio.to_thread(
                route,
                network,
                payload.origin,
                payload.destination,
                payload.departure_time,
                request.app.state.settings,
            )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"ошибка R5: {error}") from error


@app.post("/matrix", response_model=MatrixResponse)
async def public_transport_matrix(
    payload: MatrixRequest, request: Request
) -> MatrixResponse:
    network = request.app.state.network
    if network is None:
        raise HTTPException(status_code=503, detail="транспортный граф R5 не загружен")
    settings = request.app.state.settings
    if len(payload.points) > settings.matrix_max_points:
        raise HTTPException(
            status_code=422,
            detail=(
                f"матрица содержит {len(payload.points)} точек, "
                f"разрешено не более {settings.matrix_max_points}"
            ),
        )
    try:
        async with request.app.state.routing_lock:
            return await asyncio.to_thread(
                travel_time_matrix,
                network,
                payload.points,
                payload.departure_time,
                settings,
            )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"ошибка R5: {error}") from error


@app.post("/matrix-block", response_model=MatrixBlockResponse)
async def public_transport_matrix_block(
    payload: MatrixBlockRequest, request: Request
) -> MatrixBlockResponse:
    network = request.app.state.network
    if network is None:
        raise HTTPException(status_code=503, detail="транспортный граф R5 не загружен")
    settings = request.app.state.settings
    pairs = len(payload.origins) * len(payload.destinations)
    if pairs > settings.matrix_block_max_pairs:
        raise HTTPException(
            status_code=422,
            detail=f"блок содержит {pairs} пар, разрешено не более {settings.matrix_block_max_pairs}",
        )
    try:
        async with request.app.state.routing_lock:
            return await asyncio.to_thread(
                travel_time_matrix_block,
                network,
                payload.origins,
                payload.destinations,
                payload.departure_time,
                settings,
            )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"ошибка R5: {error}") from error
