from __future__ import annotations

import json

import httpx
import pytest

from app.ai_summary.config import SummaryConfig
from app.ai_summary.deepseek import DeepSeekClient
from app.ai_summary.errors import AiSummaryError


TRANSCRIPT = [
    {"start_seconds": 1.0, "end_seconds": 4.0, "text": "今天介绍反向传播"},
    {"start_seconds": 5.0, "end_seconds": 9.0, "text": "重点理解链式法则"},
]


def valid_content() -> dict:
    return {
        "overview": "视频说明反向传播与链式法则。",
        "keywords": ["反向传播", "链式法则"],
        "sections": [
            {
                "title": "基本原理",
                "summary": "通过链式法则计算梯度。",
                "points": [{"text": "理解链式法则", "start_seconds": 5}],
            }
        ],
        "key_points": [{"text": "反向传播依赖链式法则", "start_seconds": 5}],
    }


def completion_response(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": finish_reason,
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_deepseek_request_uses_json_mode_and_validates_result() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return completion_response(json.dumps(valid_content(), ensure_ascii=False))

    config = SummaryConfig(api_key="test-key", model="deepseek-flash")
    client = DeepSeekClient(config, transport=httpx.MockTransport(handler))
    result = await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)

    assert result.overview.startswith("视频说明")
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["temperature"] == 0.2
    assert captured["body"]["max_tokens"] == 8192
    assert captured["body"]["stream"] is False


@pytest.mark.asyncio
async def test_deepseek_retries_once_for_invalid_json() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return completion_response("not-json")
        return completion_response(json.dumps(valid_content(), ensure_ascii=False))

    client = DeepSeekClient(
        SummaryConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    result = await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)

    assert calls == 2
    assert result.key_points[0].start_seconds == 5


@pytest.mark.asyncio
async def test_deepseek_rejects_out_of_range_timestamp_after_retry() -> None:
    invalid = valid_content()
    invalid["key_points"][0]["start_seconds"] = 999

    client = DeepSeekClient(
        SummaryConfig(api_key="test-key"),
        transport=httpx.MockTransport(
            lambda _: completion_response(json.dumps(invalid, ensure_ascii=False))
        ),
    )

    with pytest.raises(AiSummaryError) as error:
        await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)
    assert error.value.code == "AI_BAD_RESPONSE"


@pytest.mark.asyncio
async def test_deepseek_maps_insufficient_balance_without_leaking_body() -> None:
    client = DeepSeekClient(
        SummaryConfig(api_key="test-key"),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(402, json={"error": "secret upstream details"})
        ),
    )

    with pytest.raises(AiSummaryError) as error:
        await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)
    assert error.value.code == "AI_INSUFFICIENT_BALANCE"
    assert "secret" not in error.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, "AI_REQUEST_INVALID"),
        (401, "AI_AUTH_FAILED"),
        (422, "AI_REQUEST_INVALID"),
        (429, "AI_RATE_LIMITED"),
        (500, "AI_UNAVAILABLE"),
        (503, "AI_UNAVAILABLE"),
    ],
)
async def test_deepseek_maps_stable_http_errors(
    status_code: int,
    expected_code: str,
) -> None:
    client = DeepSeekClient(
        SummaryConfig(api_key="test-key"),
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
    )

    with pytest.raises(AiSummaryError) as error:
        await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)
    assert error.value.code == expected_code


@pytest.mark.asyncio
async def test_deepseek_rejects_truncated_output() -> None:
    client = DeepSeekClient(
        SummaryConfig(api_key="test-key"),
        transport=httpx.MockTransport(
            lambda _: completion_response("{}", finish_reason="length")
        ),
    )

    with pytest.raises(AiSummaryError) as error:
        await client.summarize("测试视频", "zh-CN", 10, TRANSCRIPT)
    assert error.value.code == "AI_RESPONSE_TRUNCATED"
