from __future__ import annotations

import os
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ai_summary.captions import CaptionFetcher
from app.ai_summary.config import SummaryConfig
from app.ai_summary.deepseek import DeepSeekClient
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DEEPSEEK_TEST") != "1",
    reason="设置 RUN_LIVE_DEEPSEEK_TEST=1 才执行真实 DeepSeek 请求",
)
async def test_live_deepseek_returns_valid_summary() -> None:
    active_config = SummaryConfig.from_settings(Settings())
    result = await DeepSeekClient(active_config).summarize(
        "链式法则小课堂",
        "zh-CN",
        20,
        [
            {
                "start_seconds": 0.0,
                "end_seconds": 5.0,
                "text": "反向传播需要从输出向输入逐层计算梯度。",
            },
            {
                "start_seconds": 5.0,
                "end_seconds": 10.0,
                "text": "每一步都使用链式法则，并把局部梯度相乘。",
            },
        ],
    )

    assert result.overview
    assert result.sections
    assert result.key_points
    assert all(point.start_seconds <= 22 for point in result.key_points)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_VIDEO_SUMMARY_TEST") != "1",
    reason="设置 RUN_LIVE_VIDEO_SUMMARY_TEST=1 才执行字幕到摘要完整链路",
)
async def test_live_ted_captions_to_summary(settings, tmp_path) -> None:
    config = SummaryConfig.from_settings(settings)
    captions = await CaptionFetcher(settings, config).fetch(
        "https://www.ted.com/talks/laura_trice_remember_to_say_thank_you",
        tmp_path / "captions",
    )

    assert captions.language == "zh-cn"
    assert captions.caption_source == "author"
    assert captions.segments

    result = await DeepSeekClient(config).summarize(
        title=captions.title,
        language=captions.language,
        duration_seconds=captions.duration_seconds,
        transcript=captions.segments,
    )
    assert result.overview
    assert result.sections
    assert result.key_points


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_VIDEO_SUMMARY_TEST") != "1",
    reason="设置 RUN_LIVE_VIDEO_SUMMARY_TEST=1 才执行摘要 API 完整链路",
)
def test_live_summary_api_from_ted(settings) -> None:
    app = create_app(settings=replace(settings, job_ttl_seconds=180))
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"username": "live_reader", "password": "safe-pass-123"},
        )
        assert registered.status_code == 201
        created = client.post(
            "/api/ai-summaries",
            json={
                "url": "https://www.ted.com/talks/laura_trice_remember_to_say_thank_you"
            },
        )
        assert created.status_code == 202
        job_id = created.json()["job_id"]

        deadline = time.monotonic() + 120
        payload = created.json()
        while time.monotonic() < deadline:
            response = client.get(f"/api/ai-summaries/{job_id}")
            assert response.status_code == 200
            payload = response.json()
            if payload["status"] in {"ready", "failed", "cancelled", "expired"}:
                break
            time.sleep(0.5)

        assert payload["status"] == "ready", payload.get("error")
        assert payload["result"]["overview"]
        assert payload["result"]["key_points"]
