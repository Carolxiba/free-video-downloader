from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from ..auth.dependencies import get_current_user
from ..auth.models import UserView
from ..config import Settings
from ..url_guard import UnsafeUrlError, validate_public_url
from .config import SummaryConfig
from .manager import SummaryManager
from .models import (
    SummaryCapabilities,
    SummaryJobView,
    SummaryRequest,
)


def install_ai_summary(app: FastAPI, settings: Settings) -> SummaryManager:
    config = SummaryConfig.from_settings(settings)
    manager = SummaryManager(settings=settings, config=config)
    app.state.ai_summaries = manager
    app.include_router(_build_router(manager, config))
    return manager


def _build_router(manager: SummaryManager, config: SummaryConfig) -> APIRouter:
    @asynccontextmanager
    async def summary_lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await manager.shutdown()

    router = APIRouter(
        prefix="/api/ai-summaries",
        tags=["ai-summary"],
        lifespan=summary_lifespan,
    )

    @router.get("/capabilities", response_model=SummaryCapabilities)
    async def capabilities(
        _: UserView = Depends(get_current_user),
    ) -> SummaryCapabilities:
        return SummaryCapabilities(
            configured=config.configured,
            provider="DeepSeek",
            model=config.model,
            caption_sources=["author", "platform_auto"],
        )

    @router.post("", response_model=SummaryJobView, status_code=202)
    async def create_summary(
        payload: SummaryRequest,
        user: UserView = Depends(get_current_user),
    ) -> SummaryJobView:
        if not config.configured:
            raise _error(503, "AI_NOT_CONFIGURED", "服务端尚未配置 DeepSeek API")
        raw_url = str(payload.url)
        try:
            await validate_public_url(raw_url)
        except UnsafeUrlError as exc:
            raise _error(400, "UNSAFE_URL", str(exc)) from exc
        return await manager.create(raw_url, user.id)

    @router.get("/{job_id}", response_model=SummaryJobView)
    async def get_summary(
        job_id: str,
        user: UserView = Depends(get_current_user),
    ) -> SummaryJobView:
        job = await manager.get(job_id, user.id)
        if job is None:
            raise _error(404, "SUMMARY_NOT_FOUND", "摘要任务不存在")
        return job.to_view()

    @router.delete("/{job_id}", response_model=SummaryJobView)
    async def cancel_summary(
        job_id: str,
        user: UserView = Depends(get_current_user),
    ) -> SummaryJobView:
        job = await manager.cancel(job_id, user.id)
        if job is None:
            raise _error(404, "SUMMARY_NOT_FOUND", "摘要任务不存在")
        return job.to_view()

    return router


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
