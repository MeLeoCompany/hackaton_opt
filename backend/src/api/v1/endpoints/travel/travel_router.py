from fastapi import APIRouter, HTTPException

from src.schemas.travel import (
    TravelMatrix,
    TravelMatrixRequest,
    TravelRoute,
    TravelRouteRequest,
)
from src.services.travel import build_matrix, build_route

router = APIRouter()


@router.post("/route", response_model=TravelRoute)
async def travel_route(payload: TravelRouteRequest) -> TravelRoute:
    try:
        return await build_route(payload.points, payload.transport)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Маршрут построить не удалось: {exc}") from exc


@router.post("/matrix", response_model=TravelMatrix)
async def travel_matrix(payload: TravelMatrixRequest) -> TravelMatrix:
    try:
        return await build_matrix(
            payload.points,
            payload.transport,
            departure_time=payload.departure_time,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Матрицу построить не удалось: {exc}") from exc
