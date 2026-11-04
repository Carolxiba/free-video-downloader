from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings
from app.models import DownloadRequest
from app.ytdlp import DownloadProgress, YtDlpRunner


LIVE_VIDEO = "https://media.w3.org/2010/05/sintel/trailer.mp4"
DOUYIN_VIDEO = "https://www.douyin.com/video/6961737553342991651"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_VIDEO_TEST") != "1",
    reason="设置 RUN_LIVE_VIDEO_TEST=1 后执行公网真实下载",
)
async def test_live_public_video_download(tmp_path: Path) -> None:
    """显式开启时验证 yt-dlp、FFmpeg 与真实公网视频的完整链路。"""
    settings = Settings(
        media_root=tmp_path / "downloads",
        ffmpeg_dir=tmp_path / "missing-ffmpeg",
    )
    runner = YtDlpRunner(settings)
    info = await runner.inspect(LIVE_VIDEO, timeout_seconds=60)
    assert info.title
    assert any(option.preset == "best" for option in info.options)

    async def on_progress(_: DownloadProgress) -> None:
        return None

    output, _ = await runner.download(
        DownloadRequest(url=LIVE_VIDEO, preset="best"),
        tmp_path / "output",
        on_progress,
        timeout_seconds=600,
    )
    assert output.is_file()
    assert output.stat().st_size > 100_000


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DOUYIN_TEST") != "1",
    reason="设置 RUN_LIVE_DOUYIN_TEST=1 后执行抖音无 Cookie 下载",
)
async def test_live_douyin_download_without_user_cookies(tmp_path: Path) -> None:
    """显式开启时验证服务端自动签名和匿名 Cookie 链路。"""
    settings = Settings(
        media_root=tmp_path / "downloads",
        ffmpeg_dir=tmp_path / "missing-ffmpeg",
    )
    runner = YtDlpRunner(settings)
    info = await runner.inspect(DOUYIN_VIDEO, timeout_seconds=60)
    assert info.site == "Douyin"
    assert info.title
    assert any(option.preset == "1080p" for option in info.options)

    async def on_progress(_: DownloadProgress) -> None:
        return None

    output, _ = await runner.download(
        DownloadRequest(url=DOUYIN_VIDEO, preset="best"),
        tmp_path / "douyin",
        on_progress,
        timeout_seconds=600,
    )
    assert output.is_file()
    assert output.stat().st_size > 100_000
