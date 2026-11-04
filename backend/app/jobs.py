from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Settings
from .models import DownloadRequest, JobStatus, JobView, VideoInfo
from .ytdlp import DownloadProgress, YtDlpError, YtDlpRunner, safe_download_name


TERMINAL_STATUSES = {
    JobStatus.READY,
    JobStatus.FAILED,
    JobStatus.EXPIRED,
    JobStatus.CANCELLED,
}


@dataclass(slots=True)
class JobRecord:
    job_id: str
    request: DownloadRequest
    video: VideoInfo
    directory: Path
    created_at: float
    expires_at: float
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    file_path: Path | None = None
    file_name: str | None = None
    error: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    def to_view(self) -> JobView:
        return JobView(
            job_id=self.job_id,
            status=self.status,
            progress=round(self.progress, 1),
            downloaded_bytes=self.downloaded_bytes,
            total_bytes=self.total_bytes,
            speed_bps=self.speed_bps,
            eta_seconds=self.eta_seconds,
            file_name=self.file_name,
            error=self.error,
            expires_at=datetime.fromtimestamp(self.expires_at, UTC).isoformat(),
            download_url=(
                f"/api/downloads/{self.job_id}/file"
                if self.status == JobStatus.READY
                else None
            ),
        )


class JobManager:
    """单进程内存任务管理，保证同一时间只运行一个下载。"""

    def __init__(self, settings: Settings, runner: YtDlpRunner) -> None:
        self.settings = settings
        self.runner = runner
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.download_concurrency)

    async def create(
        self,
        request: DownloadRequest,
        video: VideoInfo,
    ) -> JobView:
        now = time.time()
        job_id = uuid.uuid4().hex
        directory = self.settings.media_root / job_id
        record = JobRecord(
            job_id=job_id,
            request=request,
            video=video,
            directory=directory,
            created_at=now,
            expires_at=now + self.settings.job_ttl_seconds,
        )
        async with self._lock:
            self._jobs[job_id] = record
        record.task = asyncio.create_task(self._run(record), name=f"download-{job_id}")
        return record.to_view()

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.status not in TERMINAL_STATUSES and record.expires_at <= time.time():
                await self._cancel_record(record)
                record.status = JobStatus.EXPIRED
                record.error = "任务已过期，请重新解析"
            return record

    async def cancel(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.status not in TERMINAL_STATUSES:
                await self._cancel_record(record)
                record.status = JobStatus.CANCELLED
                record.error = "任务已取消"
            return record

    async def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        async with self._lock:
            expired_ids = [
                job_id
                for job_id, record in self._jobs.items()
                if record.expires_at <= now
            ]
            for job_id in expired_ids:
                record = self._jobs.pop(job_id)
                if record.status not in TERMINAL_STATUSES:
                    await self._cancel_record(record)
                await asyncio.to_thread(shutil.rmtree, record.directory, True)
                removed += 1
        return removed

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [
                record.task
                for record in self._jobs.values()
                if record.task and not record.task.done()
            ]
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, record: JobRecord) -> None:
        try:
            async with self._semaphore:
                record.status = JobStatus.DOWNLOADING
                output, raw_name = await self.runner.download(
                    record.request,
                    record.directory,
                    lambda progress: self._update_progress(record, progress),
                    self.settings.download_timeout_seconds,
                )
                if record.status == JobStatus.CANCELLED:
                    await asyncio.to_thread(shutil.rmtree, record.directory, True)
                    return
                record.status = JobStatus.PROCESSING
                record.progress = 100
                extension = output.suffix.lower()
                final_path = record.directory / safe_download_name(record.video.title, extension)
                if final_path != output:
                    output.replace(final_path)
                record.file_path = final_path
                record.file_name = final_path.name
                record.status = JobStatus.READY
                record.speed_bps = None
                record.eta_seconds = 0
                record.expires_at = time.time() + self.settings.job_ttl_seconds
        except asyncio.CancelledError:
            record.status = JobStatus.CANCELLED
            record.error = "任务已取消"
            await asyncio.to_thread(shutil.rmtree, record.directory, True)
            raise
        except YtDlpError as exc:
            record.status = JobStatus.FAILED
            record.error = exc.message
            await asyncio.to_thread(shutil.rmtree, record.directory, True)
        except Exception:
            record.status = JobStatus.FAILED
            record.error = "下载遇到未知错误，请稍后重试"
            await asyncio.to_thread(shutil.rmtree, record.directory, True)

    async def _update_progress(
        self,
        record: JobRecord,
        progress: DownloadProgress,
    ) -> None:
        if record.status == JobStatus.CANCELLED:
            return
        record.progress = progress.progress
        record.downloaded_bytes = progress.downloaded_bytes
        record.total_bytes = progress.total_bytes
        record.speed_bps = progress.speed_bps
        record.eta_seconds = progress.eta_seconds

    async def _cancel_record(self, record: JobRecord) -> None:
        if record.task and not record.task.done():
            record.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await record.task

