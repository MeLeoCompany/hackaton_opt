from fastapi import APIRouter

from src.api.v1.endpoints import health, travel

router = APIRouter()
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(travel.router, prefix="/travel", tags=["travel"])
