from fastapi import APIRouter, Depends

from src.api.deps import current_user
from src.api.v1.endpoints import (
    auth,
    engineers,
    equipment,
    health,
    offices,
    plans,
    references,
    requests,
    travel,
    users,
)

router = APIRouter()
# без входа — только проверка живости и сам вход
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])

# всё остальное — только после входа; данные офиса отбирает Depends(current_office_id)
signed_in = [Depends(current_user)]
router.include_router(users.router, prefix="/users", tags=["users"], dependencies=signed_in)
router.include_router(
    references.router, prefix="/references", tags=["references"], dependencies=signed_in
)
router.include_router(offices.router, prefix="/offices", tags=["offices"], dependencies=signed_in)
router.include_router(
    equipment.router, prefix="/equipment", tags=["equipment"], dependencies=signed_in
)
router.include_router(requests.router, prefix="/requests", tags=["requests"], dependencies=signed_in)
router.include_router(
    engineers.router, prefix="/engineers", tags=["engineers"], dependencies=signed_in
)
router.include_router(plans.router, prefix="/plans", tags=["plans"], dependencies=signed_in)
router.include_router(travel.router, prefix="/travel", tags=["travel"], dependencies=signed_in)
