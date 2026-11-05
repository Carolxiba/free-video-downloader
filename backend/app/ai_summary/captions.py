from __future__ import annotations

import asyncio
import contextlib
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..config import Settings
from .config import SummaryConfig
from .errors import AiSummaryError


_TIMECODE = re.compile(
    r"(?:(?P<hours>\d+):)?(?P<minutes>\d{2}):(?P<seconds>\d{2})[.,](?P<millis>\d{3})"
)
_HTML_TAG = re.compile(r"<[^>]+>")
_ASS_STYLE = re.compile(r"\{\\[^}]+\}")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class CaptionBundle:
    source_url: str
    title: str
    duration_seconds: float | None
    caption_source: str
    language: str
    segments: list[dict[str, float | str]]


class CaptionFetcher:
    """只读取站点已有字幕，不执行语音识别。"""

    def __init__(self, settings: Settings, config: SummaryConfig) -> None:
        self.settings = settings
        self.config = config

    async def fetch(self, url: str, destination: Path) -> CaptionBundle:
        destination.mkdir(parents=True, exist_ok=True)
        cookie_args, temporary_cookie_file = self._prepare_cookie_args(url, destination)
        try:
            payload = await self._inspect_payload(url, cookie_args)
            metadata = _validate_metadata(
                payload,
                url,
                self.settings.max_duration_seconds,
            )
            selected = _select_caption(payload)
            if selected is None:
                if _is_bilibili_url(url) and not cookie_args:
                    raise AiSummaryError(
                        "BILIBILI_AUTH_REQUIRED",
                        "该 B站视频字幕需要站点服务端会话，客户无需登录",
                    )
                raise AiSummaryError(
                    "CAPTIONS_NOT_FOUND",
                    "该视频没有可读取的作者字幕或平台自动字幕",
                )

            language, source = selected
            command = [
                *self._base_command(cookie_args),
                "--skip-download",
                "--write-subs" if source == "author" else "--write-auto-subs",
                "--sub-langs",
                language,
                "--sub-format",
                "json3/vtt/srt/best",
                "--paths",
                f"home:{destination}",
                "--output",
                "caption.%(ext)s",
                "--",
                url,
            ]
            await self._run_command(command, self.config.caption_timeout_seconds)
            subtitle_file = _find_subtitle_file(destination)
            if subtitle_file is None:
                raise AiSummaryError(
                    "CAPTIONS_FETCH_FAILED",
                    "解析到了字幕信息，但字幕文件没有成功保存",
                )

            segments = parse_subtitle_file(subtitle_file)
            if not segments:
                raise AiSummaryError("CAPTIONS_EMPTY", "字幕文件里没有可用文本")

            transcript_chars = sum(len(str(item["text"])) for item in segments)
            if transcript_chars > self.config.max_transcript_chars:
                raise AiSummaryError(
                    "TRANSCRIPT_TOO_LONG",
                    "字幕文本过长，首版暂不处理这个视频",
                )

            return CaptionBundle(
                source_url=str(metadata["webpage_url"]),
                title=str(metadata["title"]),
                duration_seconds=metadata["duration"],
                caption_source=source,
                language=language,
                segments=segments,
            )
        finally:
            if temporary_cookie_file is not None:
                temporary_cookie_file.unlink(missing_ok=True)

    async def _inspect_payload(
        self,
        url: str,
        cookie_args: list[str],
    ) -> dict[str, Any]:
        command = [
            *self._base_command(cookie_args),
            "--dump-single-json",
            "--skip-download",
            "--retries",
            "2",
            "--",
            url,
        ]
        stdout, _ = await self._run_command(
            command,
            self.config.caption_timeout_seconds,
        )
        try:
            payload = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise AiSummaryError(
                "CAPTIONS_FETCH_FAILED",
                "视频字幕信息格式异常，请稍后重试",
            ) from exc
        if not isinstance(payload, dict):
            raise AiSummaryError("CAPTIONS_FETCH_FAILED", "没有获取到有效的视频信息")
        return payload

    def _base_command(self, cookie_args: list[str] | None = None) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "app.ytdlp_cli",
            "--no-playlist",
            "--no-warnings",
            "--no-colors",
            "--socket-timeout",
            "15",
        ]
        if cookie_args:
            command.extend(cookie_args)
        if self.settings.proxy_url:
            command.extend(["--proxy", self.settings.proxy_url])
        return command

    def _prepare_cookie_args(
        self,
        url: str,
        destination: Path,
    ) -> tuple[list[str], Path | None]:
        if not _is_bilibili_url(url):
            return [], None
        if self.config.bilibili_cookies_file is not None:
            cookie_file = self.config.bilibili_cookies_file.expanduser()
            if not cookie_file.is_file():
                raise AiSummaryError(
                    "BILIBILI_AUTH_INVALID",
                    "B站字幕会话文件不存在",
                )
            return ["--cookies", str(cookie_file)], None
        if not self.config.bilibili_cookie:
            return [], None

        cookie_file = destination / ".bilibili-cookies.txt"
        _write_netscape_cookie_file(cookie_file, self.config.bilibili_cookie)
        return ["--cookies", str(cookie_file)], cookie_file

    async def _run_command(
        self,
        command: list[str],
        timeout_seconds: int,
    ) -> tuple[bytes, bytes]:
        environment = os.environ.copy()
        backend_root = Path(__file__).resolve().parents[2]
        current_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(backend_root)
            if not current_path
            else f"{backend_root}{os.pathsep}{current_path}"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(backend_root),
                env=environment,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
                await process.wait()
            raise AiSummaryError(
                "CAPTIONS_TIMEOUT",
                "读取视频字幕超时，请稍后重试",
            ) from exc
        except OSError as exc:
            raise AiSummaryError(
                "CAPTIONS_FETCH_FAILED",
                "无法启动字幕解析程序",
            ) from exc

        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").lower()
            if "login required" in stderr_text or "need login" in stderr_text:
                raise AiSummaryError(
                    "CAPTIONS_LOGIN_REQUIRED",
                    "该视频字幕需要在来源站点登录后才能读取",
                )
            if "drm" in stderr_text:
                raise AiSummaryError(
                    "DRM_NOT_SUPPORTED",
                    "该视频受 DRM 保护，无法读取字幕",
                )
            raise AiSummaryError(
                "CAPTIONS_FETCH_FAILED",
                "读取视频字幕失败，请检查链接后重试",
            )
        return stdout, stderr


def _validate_metadata(
    payload: dict[str, Any],
    source_url: str,
    max_duration_seconds: int,
) -> dict[str, str | float | None]:
    if payload.get("_type") == "playlist" or payload.get("entries"):
        raise AiSummaryError("PLAYLIST_NOT_SUPPORTED", "首版只支持单个视频")
    if payload.get("is_live"):
        raise AiSummaryError("LIVE_NOT_SUPPORTED", "暂不支持直播内容")
    if payload.get("has_drm"):
        raise AiSummaryError("DRM_NOT_SUPPORTED", "该视频受 DRM 保护")

    duration = _optional_float(payload.get("duration"))
    if duration is not None and duration > max_duration_seconds:
        raise AiSummaryError("VIDEO_TOO_LONG", "视频超过 2 小时限制")
    return {
        "title": str(payload.get("title") or "未命名视频").strip(),
        "webpage_url": str(payload.get("webpage_url") or source_url),
        "duration": duration,
    }


def _select_caption(payload: dict[str, Any]) -> tuple[str, str] | None:
    candidates: list[tuple[tuple[int, int, int, str], str, str]] = []
    for source, field, source_rank in (
        ("author", "subtitles", 0),
        ("platform_auto", "automatic_captions", 1),
    ):
        captions = payload.get(field)
        if not isinstance(captions, dict):
            continue
        for language, tracks in captions.items():
            if language == "danmaku" or not tracks:
                continue
            language_text = str(language)
            candidates.append(
                (
                    (
                        _language_rank(language_text),
                        source_rank,
                        len(candidates),
                        language_text,
                    ),
                    language_text,
                    source,
                )
            )
    if not candidates:
        return None
    _, language, source = min(candidates, key=lambda item: item[0])
    return language, source


def _language_rank(language: str) -> int:
    normalized = language.replace("_", "-").lower()
    if normalized in {"zh", "zh-cn", "zh-hans", "zh-sg"}:
        return 0
    if normalized.startswith("zh"):
        return 1
    if normalized.startswith("en"):
        return 2
    return 3


def _find_subtitle_file(directory: Path) -> Path | None:
    allowed = {".json3", ".json", ".vtt", ".srt"}
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in allowed
        and path.stat().st_size > 0
    ]
    return max(candidates, key=lambda item: item.stat().st_size, default=None)


def _is_bilibili_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return (
        host == "bilibili.com"
        or host.endswith(".bilibili.com")
        or host == "b23.tv"
        or host.endswith(".b23.tv")
    )


def _write_netscape_cookie_file(path: Path, raw_cookie: str) -> None:
    """把服务端保存的 Cookie 字符串临时转换为 yt-dlp 可读取的格式。"""
    cookie_text = raw_cookie.strip()
    if cookie_text.startswith("# Netscape HTTP Cookie File"):
        content = cookie_text
    else:
        pairs: list[tuple[str, str]] = []
        for item in cookie_text.split(";"):
            name, separator, value = item.strip().partition("=")
            if not separator or not name or not value:
                continue
            if any(character in value for character in ("\t", "\r", "\n")):
                raise AiSummaryError(
                    "BILIBILI_AUTH_INVALID",
                    "B站字幕会话格式不正确",
                )
            pairs.append((name, value))
        if not pairs:
            raise AiSummaryError(
                "BILIBILI_AUTH_INVALID",
                "B站字幕会话格式不正确",
            )
        expires = int(time.time()) + 30 * 24 * 60 * 60
        content = "\n".join(
            [
                "# Netscape HTTP Cookie File",
                *[
                    f".bilibili.com\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}"
                    for name, value in pairs
                ],
                "",
            ]
        )
    path.write_text(content, encoding="utf-8")


def parse_subtitle_file(path: Path) -> list[dict[str, float | str]]:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".json3", ".json"}:
        segments = _parse_json3(content)
    else:
        segments = _parse_timed_text(content)
    return _dedupe_segments(segments)


def _parse_json3(content: str) -> list[dict[str, float | str]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AiSummaryError("CAPTIONS_INVALID", "JSON 字幕文件无法解析") from exc

    segments: list[dict[str, float | str]] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        text_parts: list[str] = []
        for segment in event.get("segs") or []:
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("utf8") or "")
            if text == "\n":
                text_parts.append(" ")
            else:
                text_parts.append(text)
        text = _clean_caption_text("".join(text_parts))
        if not text:
            continue
        start = max(0.0, float(event.get("tStartMs") or 0) / 1000)
        duration = max(0.0, float(event.get("dDurationMs") or 0) / 1000)
        end = start + (duration if duration > 0 else 1.0)
        segments.append({"start_seconds": start, "end_seconds": end, "text": text})
    return segments


def _parse_timed_text(content: str) -> list[dict[str, float | str]]:
    blocks = re.split(r"\r?\n\s*\r?\n", content.replace("\ufeff", ""))
    segments: list[dict[str, float | str]] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue
        start_match, end_match = _parse_timing_line(lines[timing_index])
        if start_match is None or end_match is None:
            continue
        text = _clean_caption_text("\n".join(lines[timing_index + 1 :]))
        if not text:
            continue
        segments.append(
            {
                "start_seconds": start_match,
                "end_seconds": max(start_match + 0.01, end_match),
                "text": text,
            }
        )
    segments.sort(key=lambda item: float(item["start_seconds"]))
    return segments


def _parse_timing_line(line: str) -> tuple[float | None, float | None]:
    parts = line.split("-->")
    if len(parts) != 2:
        return None, None
    return _parse_timecode(parts[0]), _parse_timecode(parts[1])


def _parse_timecode(value: str) -> float | None:
    match = _TIMECODE.search(value.strip())
    if match is None:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _clean_caption_text(text: str) -> str:
    text = html.unescape(_ASS_STYLE.sub("", _HTML_TAG.sub(" ", text)))
    return _WHITESPACE.sub(" ", text).strip()


def _dedupe_segments(
    source: list[dict[str, float | str]],
) -> list[dict[str, float | str]]:
    merged: list[dict[str, float | str]] = []
    for item in source:
        text = str(item["text"]).strip()
        start = float(item["start_seconds"])
        end = max(start + 0.01, float(item["end_seconds"]))
        if not text:
            continue
        if merged:
            previous = merged[-1]
            previous_text = str(previous["text"])
            if text == previous_text:
                previous["end_seconds"] = max(float(previous["end_seconds"]), end)
                continue
            if text.startswith(previous_text) and len(text) > len(previous_text):
                text = text[len(previous_text) :].strip(" ,，。.;；:：")
                if not text:
                    previous["end_seconds"] = max(float(previous["end_seconds"]), end)
                    continue
        merged.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": text,
            }
        )
    return merged


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
