from fastapi import FastAPI

from src.api.v1.router import router as v1_router
from src.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(v1_router, prefix="/api/v1")
