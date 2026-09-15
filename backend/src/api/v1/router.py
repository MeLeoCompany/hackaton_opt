from fastapi import APIRouter

from src.api.v1.endpoints import health, references, requests, travel

router = APIRouter()
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(references.router, prefix="/references", tags=["references"])
router.include_router(requests.router, prefix="/requests", tags=["requests"])
router.include_router(travel.router, prefix="/travel", tags=["travel"])
