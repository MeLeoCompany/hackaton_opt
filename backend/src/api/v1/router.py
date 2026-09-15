from fastapi import APIRouter

from src.api.v1.endpoints import engineers, health, plans, references, requests, travel

router = APIRouter()
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(references.router, prefix="/references", tags=["references"])
router.include_router(requests.router, prefix="/requests", tags=["requests"])
router.include_router(engineers.router, prefix="/engineers", tags=["engineers"])
router.include_router(plans.router, prefix="/plans", tags=["plans"])
router.include_router(travel.router, prefix="/travel", tags=["travel"])
