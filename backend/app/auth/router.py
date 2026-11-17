from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response

from ..config import Settings
from ..rate_limit import InMemoryRateLimiter
from .dependencies import SESSION_COOKIE, get_current_user
from .errors import AuthError
from .models import AuthCredentials, AuthMessage, UserView
from .service import AuthService
from .store import AuthStore


def install_auth(app: FastAPI, settings: Settings) -> AuthService:
    service = AuthService(
        store=AuthStore(settings.auth_db_path),
        session_ttl_seconds=settings.auth_session_ttl_seconds,
        cookie_secure=settings.auth_cookie_secure,
    )
    app.state.auth = service
    app.include_router(_build_router(service))
    return service


def _build_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    limiter = InMemoryRateLimiter(10, 60)

    @router.post("/register", response_model=UserView, status_code=201)
    async def register(
        payload: AuthCredentials,
        request: Request,
        response: Response,
    ) -> UserView:
        await _check_auth_rate_limit(request, limiter)
        return _run_auth(
            response,
            service,
            lambda: service.register(payload.username, payload.password),
        )

    @router.post("/login", response_model=UserView)
    async def login(
        payload: AuthCredentials,
        request: Request,
        response: Response,
    ) -> UserView:
        await _check_auth_rate_limit(request, limiter)
        return _run_auth(
            response,
            service,
            lambda: service.login(payload.username, payload.password),
        )

    @router.post("/logout", response_model=AuthMessage)
    async def logout(request: Request, response: Response) -> AuthMessage:
        service.logout(request.cookies.get(SESSION_COOKIE))
        _clear_session_cookie(response, service)
        return AuthMessage(message="已退出登录")

    @router.get("/me", response_model=UserView)
    async def me(user: UserView = Depends(get_current_user)) -> UserView:
        return user

    return router


def _run_auth(
    response: Response,
    service: AuthService,
    action: Callable[[], tuple[UserView, str, int]],
) -> UserView:
    try:
        user, token, expires_at = action()
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max(1, expires_at - int(time.time())),
        httponly=True,
        secure=service.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


def _clear_session_cookie(response: Response, service: AuthService) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=service.cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def _check_auth_rate_limit(
    request: Request,
    limiter: InMemoryRateLimiter,
) -> None:
    client_key = request.client.host if request.client else "unknown"
    if not await limiter.allow(client_key):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "AUTH_RATE_LIMITED",
                "message": "登录尝试过于频繁，请稍后再试",
            },
        )
