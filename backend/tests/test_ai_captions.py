from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai_summary.config import SummaryConfig
from app.ai_summary.captions import (
    CaptionFetcher,
    _select_caption,
    _write_netscape_cookie_file,
    parse_subtitle_file,
)
from app.config import Settings


def test_vtt_parser_keeps_timestamps_and_removes_overlap(tmp_path) -> None:
    subtitle = tmp_path / "captions.zh.vtt"
    subtitle.write_text(
        """WEBVTT

00:00:01.000 --> 00:00:03.000
<c>第一句</c>

00:00:03.000 --> 00:00:05.500
第一句，第二句

00:00:06.000 --> 00:00:08.000
第三句
""",
        encoding="utf-8",
    )

    segments = parse_subtitle_file(subtitle)

    assert [item["text"] for item in segments] == ["第一句", "第二句", "第三句"]
    assert segments[1]["start_seconds"] == 3
    assert segments[2]["end_seconds"] == 8


def test_srt_parser_supports_comma_milliseconds(tmp_path) -> None:
    subtitle = tmp_path / "captions.en.srt"
    subtitle.write_text(
        """1
00:00:01,250 --> 00:00:02,750
Hello &amp; welcome

2
00:00:02,750 --> 00:00:04,000
Hello &amp; welcome to the lesson
""",
        encoding="utf-8",
    )

    segments = parse_subtitle_file(subtitle)

    assert segments[0]["start_seconds"] == 1.25
    assert segments[0]["text"] == "Hello & welcome"
    assert segments[1]["text"] == "to the lesson"


def test_json3_parser_removes_caption_layout_markers(tmp_path) -> None:
    subtitle = tmp_path / "captions.zh.json3"
    subtitle.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 1500,
                        "dDurationMs": 2500,
                        "segs": [
                            {"utf8": "核心"},
                            {"utf8": "\n"},
                            {"utf8": "内容"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    segments = parse_subtitle_file(subtitle)

    assert segments == [
        {"start_seconds": 1.5, "end_seconds": 4.0, "text": "核心 内容"}
    ]


def test_caption_priority_prefers_chinese_author_then_auto_then_english() -> None:
    payload = {
        "subtitles": {
            "en": [{"ext": "vtt"}],
            "zh-CN": [{"ext": "vtt"}],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "vtt"}],
            "ja": [{"ext": "vtt"}],
        },
    }

    assert _select_caption(payload) == ("zh-CN", "author")
    payload["subtitles"] = {"en": [{"ext": "vtt"}]}
    assert _select_caption(payload) == ("zh-Hans", "platform_auto")
    payload["automatic_captions"] = {"ja": [{"ext": "vtt"}]}
    assert _select_caption(payload) == ("en", "author")


def test_caption_priority_prefers_simplified_chinese_track() -> None:
    payload = {
        "subtitles": {
            "zh-tw": [{"ext": "vtt"}],
            "zh-cn": [{"ext": "vtt"}],
        }
    }

    assert _select_caption(payload) == ("zh-cn", "author")


def test_danmaku_is_never_treated_as_a_caption() -> None:
    assert _select_caption({"subtitles": {"danmaku": [{"ext": "xml"}]}}) is None


def test_bilibili_cookie_string_is_written_as_netscape_file(tmp_path) -> None:
    cookie_file = tmp_path / ".bilibili-cookies.txt"

    _write_netscape_cookie_file(
        cookie_file,
        "SESSDATA=session-value; bili_jct=csrf-value; buvid3=device-value",
    )

    content = cookie_file.read_text(encoding="utf-8")
    assert content.startswith("# Netscape HTTP Cookie File")
    assert "\tSESSDATA\tsession-value" in content
    assert "\tbili_jct\tcsrf-value" in content
    assert "\tbuvid3\tdevice-value" in content


@pytest.mark.asyncio
async def test_bilibili_cookie_is_used_only_for_subprocess_and_removed(
    settings: Settings,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "captions"
    config = SummaryConfig(
        api_key="test-key",
        bilibili_cookie="SESSDATA=session-value; bili_jct=csrf-value",
    )
    fetcher = CaptionFetcher(settings, config)
    commands: list[list[str]] = []

    async def fake_run(command: list[str], timeout_seconds: int):
        del timeout_seconds
        commands.append(command)
        if len(commands) == 1:
            payload = {
                "id": "BV-test",
                "title": "B站测试视频",
                "webpage_url": "https://www.bilibili.com/video/BV-test",
                "duration": 60,
                "subtitles": {"zh-cn": [{"ext": "vtt"}]},
            }
            return json.dumps(payload, ensure_ascii=False).encode(), b""
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "caption.zh-cn.vtt").write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n测试字幕\n",
            encoding="utf-8",
        )
        return b"", b""

    fetcher._run_command = fake_run  # type: ignore[method-assign]
    result = await fetcher.fetch(
        "https://www.bilibili.com/video/BV-test",
        destination,
    )

    cookie_path = destination / ".bilibili-cookies.txt"
    assert all("--cookies" in command for command in commands)
    assert not cookie_path.exists()
    assert result.caption_source == "author"
    assert result.segments[0]["text"] == "测试字幕"
