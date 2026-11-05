from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import Settings
from .captions import CaptionBundle, CaptionFetcher
from .config import SummaryConfig
from .deepseek import DeepSeekClient
from .errors import AiSummaryError
from .models import SummaryJobView, SummaryResult, SummaryStatus


TERMINAL_STATUSES = {
    SummaryStatus.READY,
    SummaryStatus.FAILED,
    SummaryStatus.CANCELLED,
    SummaryStatus.EXPIRED,
}


@dataclass(slots=True)
class SummaryJob:
    job_id: str
    url: str
    directory: Path
    created_at: float
    expires_at: float
    status: SummaryStatus = SummaryStatus.QUEUED
    progress: float = 0
    stage: str | None = "等待开始"
    result: SummaryResult | None = None
    error_code: str | None = None
    error: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    def to_view(self) -> SummaryJobView:
        return SummaryJobView(
            job_id=self.job_id,
            status=self.status,
            progress=round(self.progress, 1),
            stage=self.stage,
            result=self.result,
            error_code=self.error_code,
            error=self.error,
            expires_at=datetime.fromtimestamp(self.expires_at, UTC).isoformat(),
        )


class SummaryManager:
    """独立的内存摘要任务，不影响现有下载队列。"""

    def __init__(
        self,
        settings: Settings,
        config: SummaryConfig,
        caption_fetcher: CaptionFetcher | None = None,
        deepseek_client: DeepSeekClient | None = None,
    ) -> None:
        self.settings = settings
        self.config = config
        self.caption_fetcher = caption_fetcher or CaptionFetcher(settings, config)
        self.deepseek_client = deepseek_client or DeepSeekClient(config)
        self._jobs: dict[str, SummaryJob] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._cleanup_task: asyncio.Task[None] | None = None

    async def create(self, url: str) -> SummaryJobView:
        self._ensure_cleanup_loop()
        await self.cleanup_expired()
        now = time.time()
        job_id = uuid.uuid4().hex
        job = SummaryJob(
            job_id=job_id,
            url=url,
            directory=self.config.root / job_id,
            created_at=now,
            expires_at=now + self.config.job_ttl_seconds,
        )
        async with self._lock:
            self._jobs[job_id] = job
        job.task = asyncio.create_task(self._run(job), name=f"ai-summary-{job_id}")
        return job.to_view()

    async def get(self, job_id: str) -> SummaryJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status not in TERMINAL_STATUSES and job.expires_at <= time.time():
                await self._cancel_record(job)
                job.status = SummaryStatus.EXPIRED
                job.stage = "任务已过期"
                job.error_code = "SUMMARY_EXPIRED"
                job.error = "摘要任务已过期，请重新生成"
            return job

    async def cancel(self, job_id: str) -> SummaryJob | None:
        await self.cleanup_expired()
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status not in TERMINAL_STATUSES:
                await self._cancel_record(job)
                job.status = SummaryStatus.CANCELLED
                job.stage = "已取消"
                job.error_code = "SUMMARY_CANCELLED"
                job.error = "AI 摘要已取消"
            return job

    async def cleanup_expired(self) -> int:
        expired: list[SummaryJob] = []
        now = time.time()
        async with self._lock:
            expired_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.expires_at <= now
            ]
            for job_id in expired_ids:
                expired.append(self._jobs.pop(job_id))
        for job in expired:
            if job.status not in TERMINAL_STATUSES:
                await self._cancel_record(job)
            await asyncio.to_thread(shutil.rmtree, job.directory, True)
        return len(expired)

    async def shutdown(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        async with self._lock:
            tasks = [
                job.task
                for job in self._jobs.values()
                if job.task and not job.task.done()
            ]
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._cleanup_task:
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    def _ensure_cleanup_loop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="ai-summary-cleanup",
        )

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            with contextlib.suppress(Exception):
                await self.cleanup_expired()

    async def _run(self, job: SummaryJob) -> None:
        try:
            async with self._semaphore:
                job.status = SummaryStatus.FETCHING_CAPTIONS
                job.progress = 10
                job.stage = "正在读取平台字幕"
                captions = await self.caption_fetcher.fetch(job.url, job.directory)
                if job.status == SummaryStatus.CANCELLED:
                    return
                job.status = SummaryStatus.SUMMARIZING
                job.progress = 55
                job.stage = "DeepSeek 正在整理大纲与要点"
                content = await self.deepseek_client.summarize(
                    title=captions.title,
                    language=captions.language,
                    duration_seconds=captions.duration_seconds,
                    transcript=captions.segments,
                )
                if job.status == SummaryStatus.CANCELLED:
                    return
                job.result = SummaryResult(
                    **content.model_dump(),
                    transcript=captions.segments,
                    caption_source=captions.caption_source,
                    language=captions.language,
                    model=self.config.model,
                    created_at=datetime.now(UTC),
                )
                job.progress = 100
                job.stage = "摘要已生成"
                job.status = SummaryStatus.READY
                job.expires_at = time.time() + self.config.job_ttl_seconds
        except asyncio.CancelledError:
            job.status = SummaryStatus.CANCELLED
            job.stage = "已取消"
            job.error_code = "SUMMARY_CANCELLED"
            job.error = "AI 摘要已取消"
            await asyncio.to_thread(shutil.rmtree, job.directory, True)
            raise
        except AiSummaryError as exc:
            job.status = SummaryStatus.FAILED
            job.stage = "生成失败"
            job.error_code = exc.code
            job.error = exc.message
            await asyncio.to_thread(shutil.rmtree, job.directory, True)
        except Exception:
            job.status = SummaryStatus.FAILED
            job.stage = "生成失败"
            job.error_code = "SUMMARY_FAILED"
            job.error = "AI 摘要遇到未知错误，请稍后重试"
            await asyncio.to_thread(shutil.rmtree, job.directory, True)
        finally:
            if job.status in {SummaryStatus.READY, SummaryStatus.FAILED}:
                await asyncio.to_thread(shutil.rmtree, job.directory, True)

    async def _cancel_record(self, job: SummaryJob) -> None:
        if job.task and not job.task.done():
            job.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await job.task
