from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai_summary.router import install_ai_summary
from .auth.dependencies import get_current_user
from .auth.models import UserView
from .auth.router import install_auth
from .config import Settings
from .jobs import JobManager
from .models import (
    ApiError,
    DownloadRequest,
    HealthView,
    InspectRequest,
    JobStatus,
    JobView,
    VideoInfo,
)
from .rate_limit import InMemoryRateLimiter
from .url_guard import UnsafeUrlError, validate_public_url
from .ytdlp import YtDlpError, YtDlpRunner, yt_dlp_version


INSPECTION_CACHE_SECONDS = 300


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def create_app(
    settings: Settings | None = None,
    runner: YtDlpRunner | None = None,
) -> FastAPI:
    active_settings = settings or Settings()
    active_runner = runner or YtDlpRunner(active_settings)
    jobs = JobManager(active_settings, active_runner)
    limiter = InMemoryRateLimiter(
        active_settings.inspect_rate_limit,
        active_settings.inspect_rate_window_seconds,
    )
    inspections: dict[tuple[str, str], tuple[float, VideoInfo]] = {}

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        active_settings.media_root.mkdir(parents=True, exist_ok=True)

        async def cleanup_loop() -> None:
            while True:
                await asyncio.sleep(30)
                with contextlib.suppress(Exception):
                    await jobs.cleanup_expired()
                    cutoff = time.time() - INSPECTION_CACHE_SECONDS
                    for url, (created_at, _) in list(inspections.items()):
                        if created_at < cutoff:
                            inspections.pop(url, None)

        cleanup_task = asyncio.create_task(cleanup_loop(), name="runtime-cleanup")
        try:
            yield
        finally:
            cleanup_task.cancel()
            await jobs.shutdown()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task

    app = FastAPI(
        title="拾帧 API",
        version="0.1.0",
        lifespan=lifespan,
        responses={400: {"model": ApiError}, 429: {"model": ApiError}},
    )
    app.state.settings = active_settings
    app.state.runner = active_runner
    app.state.jobs = jobs
    install_auth(app, active_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    install_ai_summary(app, active_settings)

    @app.get("/api/health", response_model=HealthView)
    async def health() -> HealthView:
        ffmpeg = active_settings.ffmpeg_path
        return HealthView(
            status="ok",
            yt_dlp_version=yt_dlp_version(),
            ffmpeg_available=ffmpeg is not None,
            ffmpeg_path=str(ffmpeg) if ffmpeg else None,
        )

    @app.post("/api/inspect", response_model=VideoInfo)
    async def inspect_video(
        payload: InspectRequest,
        request: Request,
        user: UserView = Depends(get_current_user),
    ) -> VideoInfo:
        client_key = request.client.host if request.client else "unknown"
        if not await limiter.allow(client_key):
            raise _error(429, "RATE_LIMITED", "操作太频繁，请稍后再试")
        raw_url = str(payload.url)
        try:
            await validate_public_url(raw_url)
        except UnsafeUrlError as exc:
            raise _error(400, "UNSAFE_URL", str(exc)) from exc

        try:
            video = await active_runner.inspect(
                raw_url,
                timeout_seconds=active_settings.inspect_timeout_seconds,
            )
        except YtDlpError as exc:
            raise _error(422, exc.code, exc.message) from exc

        inspections[(user.id, raw_url)] = (time.time(), video)
        return video

    @app.post("/api/downloads", response_model=JobView, status_code=202)
    async def create_download(
        payload: DownloadRequest,
        user: UserView = Depends(get_current_user),
    ) -> JobView:
        raw_url = str(payload.url)
        try:
            await validate_public_url(raw_url)
        except UnsafeUrlError as exc:
            raise _error(400, "UNSAFE_URL", str(exc)) from exc

        cached = inspections.get((user.id, raw_url))
        if cached is None or cached[0] < time.time() - INSPECTION_CACHE_SECONDS:
            raise _error(409, "INSPECT_REQUIRED", "请先解析视频，再开始下载")
        video = cached[1]
        if payload.preset not in {option.preset for option in video.options}:
            raise _error(422, "FORMAT_UNAVAILABLE", "当前视频不支持所选画质")
        return await jobs.create(payload, video, user.id)

    @app.get("/api/downloads/{job_id}", response_model=JobView)
    async def get_download(
        job_id: str,
        user: UserView = Depends(get_current_user),
    ) -> JobView:
        record = await jobs.get(job_id, user.id)
        if record is None:
            raise _error(404, "JOB_NOT_FOUND", "下载任务不存在")
        return record.to_view()

    @app.delete("/api/downloads/{job_id}", response_model=JobView)
    async def cancel_download(
        job_id: str,
        user: UserView = Depends(get_current_user),
    ) -> JobView:
        record = await jobs.cancel(job_id, user.id)
        if record is None:
            raise _error(404, "JOB_NOT_FOUND", "下载任务不存在")
        return record.to_view()

    @app.get("/api/downloads/{job_id}/file")
    async def download_file(
        job_id: str,
        user: UserView = Depends(get_current_user),
    ) -> FileResponse:
        record = await jobs.get(job_id, user.id)
        if record is None:
            raise _error(404, "JOB_NOT_FOUND", "下载任务不存在")
        if record.status == JobStatus.EXPIRED:
            raise _error(410, "JOB_EXPIRED", "文件已过期，请重新下载")
        if record.status != JobStatus.READY or record.file_path is None:
            raise _error(409, "JOB_NOT_READY", "文件尚未生成")
        if not record.file_path.is_file():
            raise _error(410, "FILE_MISSING", "文件已失效，请重新下载")
        return FileResponse(
            record.file_path,
            filename=record.file_name or record.file_path.name,
            media_type=_media_type(record.file_path),
        )

    if active_settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=active_settings.frontend_dist, html=True),
            name="frontend",
        )

    return app


def _media_type(path: Path) -> str:
    return "audio/mpeg" if path.suffix.lower() == ".mp3" else "video/mp4"


app = create_app()
