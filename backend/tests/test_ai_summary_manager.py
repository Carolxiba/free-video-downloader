from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.ai_summary.captions import CaptionBundle
from app.ai_summary.config import SummaryConfig
from app.ai_summary.errors import AiSummaryError
from app.ai_summary.manager import SummaryManager
from app.ai_summary.models import SummaryContent, SummaryStatus


class FakeCaptionFetcher:
    def __init__(self) -> None:
        self.error: AiSummaryError | None = None

    async def fetch(self, url: str, destination: Path) -> CaptionBundle:
        if self.error:
            raise self.error
        return CaptionBundle(
            source_url=url,
            title="AI 测试视频",
            duration_seconds=20,
            caption_source="author",
            language="zh-CN",
            segments=[
                {"start_seconds": 1.0, "end_seconds": 4.0, "text": "第一段内容"},
                {"start_seconds": 8.0, "end_seconds": 12.0, "text": "第二段内容"},
            ],
        )


class FakeDeepSeekClient:
    async def summarize(self, **_: object) -> SummaryContent:
        return SummaryContent(
            overview="这是一个测试摘要。",
            keywords=["测试", "摘要"],
            sections=[
                {
                    "title": "测试章节",
                    "summary": "章节内容。",
                    "points": [{"text": "关键点", "start_seconds": 8}],
                }
            ],
            key_points=[{"text": "核心结论", "start_seconds": 8}],
        )


class BlockingCaptionFetcher(FakeCaptionFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self, url: str, destination: Path) -> CaptionBundle:
        self.started.set()
        await self.release.wait()
        return await super().fetch(url, destination)


async def wait_for_status(
    manager: SummaryManager,
    job_id: str,
    status: SummaryStatus,
) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = await manager.get(job_id)
        if job and job.status == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"任务未进入 {status}")


@pytest.mark.asyncio
async def test_summary_manager_completes_without_touching_downloads(settings, tmp_path) -> None:
    config = SummaryConfig(
        api_key="test-key",
        root=tmp_path / "summaries",
    )
    manager = SummaryManager(
        settings,
        config,
        caption_fetcher=FakeCaptionFetcher(),  # type: ignore[arg-type]
        deepseek_client=FakeDeepSeekClient(),  # type: ignore[arg-type]
    )
    try:
        created = await manager.create("https://8.8.8.8/video")
        await wait_for_status(manager, created.job_id, SummaryStatus.READY)
        job = await manager.get(created.job_id)
        assert job is not None
        assert job.result is not None
        assert job.result.transcript[1].text == "第二段内容"
        assert job.result.caption_source == "author"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_summary_manager_exposes_caption_failure(settings, tmp_path) -> None:
    fetcher = FakeCaptionFetcher()
    fetcher.error = AiSummaryError("CAPTIONS_NOT_FOUND", "没有字幕")
    manager = SummaryManager(
        settings,
        SummaryConfig(api_key="test-key", root=tmp_path / "summaries"),
        caption_fetcher=fetcher,  # type: ignore[arg-type]
        deepseek_client=FakeDeepSeekClient(),  # type: ignore[arg-type]
    )
    try:
        created = await manager.create("https://8.8.8.8/video")
        await wait_for_status(manager, created.job_id, SummaryStatus.FAILED)
        job = await manager.get(created.job_id)
        assert job is not None
        assert job.error_code == "CAPTIONS_NOT_FOUND"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_summary_manager_cleans_expired_jobs(settings, tmp_path) -> None:
    config = replace(
        SummaryConfig(api_key="test-key", root=tmp_path / "summaries"),
        job_ttl_seconds=1,
    )
    manager = SummaryManager(
        settings,
        config,
        caption_fetcher=FakeCaptionFetcher(),  # type: ignore[arg-type]
        deepseek_client=FakeDeepSeekClient(),  # type: ignore[arg-type]
    )
    try:
        created = await manager.create("https://8.8.8.8/video")
        await wait_for_status(manager, created.job_id, SummaryStatus.READY)
        job = manager._jobs[created.job_id]
        job.expires_at = time.time() - 1
        assert await manager.cleanup_expired() == 1
        assert await manager.get(created.job_id) is None
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_summary_manager_can_cancel_running_job(settings, tmp_path) -> None:
    fetcher = BlockingCaptionFetcher()
    manager = SummaryManager(
        settings,
        SummaryConfig(api_key="test-key", root=tmp_path / "summaries"),
        caption_fetcher=fetcher,  # type: ignore[arg-type]
        deepseek_client=FakeDeepSeekClient(),  # type: ignore[arg-type]
    )
    try:
        created = await manager.create("https://8.8.8.8/video")
        await asyncio.wait_for(fetcher.started.wait(), timeout=1)
        cancelled = await manager.cancel(created.job_id)
        assert cancelled is not None
        assert cancelled.status == SummaryStatus.CANCELLED
    finally:
        fetcher.release.set()
        await manager.shutdown()
