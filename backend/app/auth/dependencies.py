from __future__ import annotations

from fastapi import HTTPException, Request

from .models import UserView


SESSION_COOKIE = "shizhen_session"


async def get_current_user(request: Request) -> UserView:
    service = getattr(request.app.state, "auth", None)
    user = service.resolve(request.cookies.get(SESSION_COOKIE)) if service else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "请先登录后再使用此功能"},
        )
    return user
