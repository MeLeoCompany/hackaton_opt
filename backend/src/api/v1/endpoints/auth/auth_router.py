"""Вход и «кто я». Остальные эндпоинты требуют токен из /auth/login."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import current_user
from src.db.session import get_db
from src.models import AppUser
from src.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from src.services.auth import auth_service
from src.services.auth.auth_service import AuthError

router = APIRouter()


@router.post("/login", response_model=LoginResponse, summary="Войти: токен и данные учётки")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)):
    try:
        return await auth_service.login(session, payload.login, payload.password)
    except AuthError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error


@router.get("/me", response_model=CurrentUser, summary="Кто вошёл")
async def me(user: AppUser = Depends(current_user), session: AsyncSession = Depends(get_db)):
    return await auth_service.to_current_user(session, user)
