from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.jobs import JobManager
from app.models import DownloadRequest, JobStatus, QualityOption, VideoInfo
from app.ytdlp import DownloadProgress


def video() -> VideoInfo:
    return VideoInfo(
        url="https://8.8.8.8/video",
        title="并发测试",
        site="Test",
        options=[
            QualityOption(
                preset="best",
                label="最佳画质",
                detail="测试",
                ext="mp4",
            )
        ],
    )


def request() -> DownloadRequest:
    return DownloadRequest(url="https://8.8.8.8/video", preset="best")


class ControlledRunner:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.started = 0
        self.release = asyncio.Event()

    async def download(
        self,
        request: DownloadRequest,
        destination: Path,
        on_progress,
        timeout_seconds: int,
    ) -> tuple[Path, str]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started += 1
        try:
            await on_progress(
                DownloadProgress(
                    progress=25,
                    downloaded_bytes=25,
                    total_bytes=100,
                    speed_bps=10,
                    eta_seconds=8,
                )
            )
            await self.release.wait()
            destination.mkdir(parents=True, exist_ok=True)
            output = destination / "media.mp4"
            output.write_bytes(b"video")
            return output, output.name
        finally:
            self.active -= 1


async def wait_for(predicate, timeout: float = 2) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("等待条件超时")


@pytest.mark.asyncio
async def test_only_one_download_runs_at_a_time(settings: Settings) -> None:
    runner = ControlledRunner()
    manager = JobManager(settings, runner)  # type: ignore[arg-type]
    try:
        first = await manager.create(request(), video())
        second = await manager.create(request(), video())
        await wait_for(lambda: runner.started == 1)

        assert (await manager.get(first.job_id)).status == JobStatus.DOWNLOADING  # type: ignore[union-attr]
        assert (await manager.get(second.job_id)).status == JobStatus.QUEUED  # type: ignore[union-attr]

        runner.release.set()
        await wait_for(
            lambda: manager._jobs[first.job_id].status == JobStatus.READY
            and manager._jobs[second.job_id].status == JobStatus.READY
        )
        assert runner.max_active == 1
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_cancel_stops_active_job(settings: Settings) -> None:
    runner = ControlledRunner()
    manager = JobManager(settings, runner)  # type: ignore[arg-type]
    try:
        created = await manager.create(request(), video())
        await wait_for(lambda: runner.started == 1)
        cancelled = await manager.cancel(created.job_id)
        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_cleanup_removes_expired_task_directory(settings: Settings) -> None:
    short_settings = replace(settings, job_ttl_seconds=1)
    runner = ControlledRunner()
    runner.release.set()
    manager = JobManager(short_settings, runner)  # type: ignore[arg-type]
    try:
        created = await manager.create(request(), video())
        await wait_for(lambda: manager._jobs[created.job_id].status == JobStatus.READY)
        record = manager._jobs[created.job_id]
        record.expires_at = time.time() - 1
        assert await manager.cleanup_expired() == 1
        assert not record.directory.exists()
        assert await manager.get(created.job_id) is None
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_download_jobs_are_isolated_by_user(settings: Settings) -> None:
    runner = ControlledRunner()
    runner.release.set()
    manager = JobManager(settings, runner)  # type: ignore[arg-type]
    try:
        created = await manager.create(request(), video(), "user-one")
        await wait_for(lambda: manager._jobs[created.job_id].status == JobStatus.READY)
        assert await manager.get(created.job_id, "user-one") is not None
        assert await manager.get(created.job_id, "user-two") is None
        assert await manager.cancel(created.job_id, "user-two") is None
    finally:
        await manager.shutdown()

