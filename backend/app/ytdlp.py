from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .models import DownloadRequest, Preset, QualityOption, VideoInfo


ProgressCallback = Callable[["DownloadProgress"], Awaitable[None]]


class YtDlpError(RuntimeError):
    """yt-dlp 调用失败，并附带适合展示给用户的错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class DownloadProgress:
    progress: float
    downloaded_bytes: int | None
    total_bytes: int | None
    speed_bps: float | None
    eta_seconds: int | None


def yt_dlp_version() -> str | None:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return None


class YtDlpRunner:
    """以子进程方式封装官方 yt-dlp，不把用户输入拼进 shell 命令。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _base_command(self) -> list[str]:
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
        if self.settings.proxy_url:
            command.extend(["--proxy", self.settings.proxy_url])
        return command

    def _subprocess_options(self) -> dict[str, object]:
        """确保 yt-dlp 子进程从后端目录导入本地兼容层。"""
        backend_root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        current_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(backend_root)
            if not current_path
            else f"{backend_root}{os.pathsep}{current_path}"
        )
        return {"cwd": str(backend_root), "env": environment}

    async def inspect(self, url: str, timeout_seconds: int) -> VideoInfo:
        if yt_dlp_version() is None:
            raise YtDlpError("YTDLP_MISSING", "服务端尚未安装 yt-dlp")

        command = [
            *self._base_command(),
            "--dump-single-json",
            "--skip-download",
            "--retries",
            "2",
            "--fragment-retries",
            "2",
            "--",
            url,
        ]
        stdout = b""
        for attempt in range(4):
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **self._subprocess_options(),
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
            except TimeoutError as exc:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                    await process.wait()
                if attempt < 3:
                    await asyncio.sleep(2 + attempt)
                    continue
                raise YtDlpError(
                    "INSPECT_TIMEOUT", "解析超时，请检查链接后重试"
                ) from exc
            except OSError as exc:
                raise YtDlpError("YTDLP_START_FAILED", "无法启动视频解析程序") from exc

            if process.returncode == 0:
                break

            stderr_text = stderr.decode("utf-8", errors="replace")
            mapped_error = _map_process_error(stderr_text)
            if attempt < 3 and _is_transient_network_error(stderr_text):
                await asyncio.sleep(2 + attempt)
                continue
            raise mapped_error

        try:
            payload = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise YtDlpError("BAD_RESPONSE", "视频信息格式异常，请稍后重试") from exc

        return _video_info_from_payload(payload, url, self.settings)

    async def download(
        self,
        request: DownloadRequest,
        destination: Path,
        on_progress: ProgressCallback,
        timeout_seconds: int,
    ) -> tuple[Path, str]:
        if yt_dlp_version() is None:
            raise YtDlpError("YTDLP_MISSING", "服务端尚未安装 yt-dlp")

        destination.mkdir(parents=True, exist_ok=True)
        format_args = _format_args(request.preset)
        progress_template = (
            "download:FZ_PROGRESS:%(progress.status)s|"
            "%(progress.downloaded_bytes)s|"
            "%(progress.total_bytes)s|"
            "%(progress.total_bytes_estimate)s|"
            "%(progress.speed)s|"
            "%(progress.eta)s"
        )
        command = [
            *self._base_command(),
            "--no-simulate",
            "--newline",
            "--progress",
            "--progress-delta",
            "0.5",
            "--progress-template",
            progress_template,
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--max-filesize",
            str(self.settings.max_file_bytes),
            "--paths",
            f"home:{destination}",
            "--output",
            "media.%(ext)s",
            *format_args,
        ]
        ffmpeg_path = self.settings.ffmpeg_path
        if ffmpeg_path is not None:
            ffmpeg_dir = ffmpeg_path.parent
            command.extend(["--ffmpeg-location", str(ffmpeg_dir)])
        command.extend(["--", str(request.url)])

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **self._subprocess_options(),
            )
        except OSError as exc:
            raise YtDlpError("YTDLP_START_FAILED", "无法启动下载程序") from exc

        stderr_chunks: list[str] = []
        stderr_size = 0

        async def consume_stdout() -> None:
            assert process.stdout is not None
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                progress = _parse_progress(line)
                if progress is not None:
                    await on_progress(progress)

        async def consume_stderr() -> None:
            nonlocal stderr_size
            assert process.stderr is not None
            async for raw_line in process.stderr:
                text = raw_line.decode("utf-8", errors="replace")
                if stderr_size < 16_384:
                    stderr_chunks.append(text)
                    stderr_size += len(text)

        readers = asyncio.gather(consume_stdout(), consume_stderr())
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            await readers
        except TimeoutError as exc:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
                await process.wait()
            await asyncio.gather(consume_stdout(), consume_stderr(), return_exceptions=True)
            raise YtDlpError("DOWNLOAD_TIMEOUT", "下载超时，请稍后重试") from exc
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
                await process.wait()
            readers.cancel()
            await asyncio.gather(readers, return_exceptions=True)
            raise

        if process.returncode != 0:
            raise _map_process_error("".join(stderr_chunks))

        output = _find_output_file(destination)
        if output is None:
            raise YtDlpError("NO_OUTPUT", "下载完成但未找到视频文件")
        if output.stat().st_size > self.settings.max_file_bytes:
            output.unlink(missing_ok=True)
            raise YtDlpError("FILE_TOO_LARGE", "视频文件超过大小限制")
        return output, output.name


def _format_args(preset: Preset) -> list[str]:
    if preset == "audio":
        return [
            "--format",
            "ba/b",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
        ]

    selector = {
        "best": "bv*+ba/b",
        "1080p": (
            "bv*[height<=1920][width<=1080]+ba/"
            "b[height<=1920][width<=1080]/"
            "bv*[height<=1080][width<=1920]+ba/"
            "b[height<=1080][width<=1920]/b"
        ),
        "720p": (
            "bv*[height<=1280][width<=720]+ba/"
            "b[height<=1280][width<=720]/"
            "bv*[height<=720][width<=1280]+ba/"
            "b[height<=720][width<=1280]/b"
        ),
    }[preset]
    return [
        "--format",
        selector,
        "--merge-output-format",
        "mp4",
    ]


def _parse_progress(line: str) -> DownloadProgress | None:
    prefix = "FZ_PROGRESS:"
    if prefix not in line:
        return None
    payload = line.split(prefix, 1)[1]
    parts = payload.split("|")
    if len(parts) != 6:
        return None

    downloaded = _optional_int(parts[1])
    total = _optional_int(parts[2]) or _optional_int(parts[3])
    speed = _optional_float(parts[4])
    eta = _optional_int(parts[5])
    percent = 0.0
    if downloaded is not None and total:
        percent = min(100.0, downloadable_percentage(downloaded, total))

    return DownloadProgress(
        progress=percent,
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed_bps=speed,
        eta_seconds=eta,
    )


def downloadable_percentage(downloaded: int, total: int) -> float:
    return round(downloaded / total * 100, 1)


def _optional_int(value: str) -> int | None:
    if value in {"NA", "None", ""}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _optional_float(value: str) -> float | None:
    if value in {"NA", "None", ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _find_output_file(directory: Path) -> Path | None:
    ignored_suffixes = {".part", ".ytdl", ".temp", ".json", ".jpg", ".jpeg", ".webp", ".png"}
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and not any(str(path).endswith(suffix) for suffix in ignored_suffixes)
        and path.stat().st_size > 0
    ]
    return max(candidates, key=lambda path: path.stat().st_size, default=None)


def _video_info_from_payload(payload: dict[str, Any], source_url: str, settings: Settings) -> VideoInfo:
    if payload.get("_type") == "playlist" or payload.get("entries"):
        raise YtDlpError("PLAYLIST_NOT_SUPPORTED", "首版只支持单个视频，不支持播放列表")
    if payload.get("is_live"):
        raise YtDlpError("LIVE_NOT_SUPPORTED", "暂不支持直播内容")
    if payload.get("has_drm"):
        raise YtDlpError("DRM_NOT_SUPPORTED", "该内容受 DRM 保护，无法下载")

    duration = _as_int(payload.get("duration"))
    if duration is not None and duration > settings.max_duration_seconds:
        raise YtDlpError("VIDEO_TOO_LONG", "视频超过 2 小时限制")

    title = str(payload.get("title") or "未命名视频").strip()
    formats = [item for item in payload.get("formats") or [] if isinstance(item, dict)]
    options = _build_quality_options(formats, duration)
    site = (
        payload.get("extractor_key")
        or payload.get("extractor")
        or payload.get("webpage_url_domain")
        or "视频站点"
    )
    thumbnail = payload.get("thumbnail")
    webpage_url = payload.get("webpage_url") or source_url

    return VideoInfo(
        url=str(webpage_url),
        title=title,
        thumbnail=str(thumbnail) if thumbnail else None,
        uploader=(
            str(payload.get("uploader") or payload.get("channel") or "").strip() or None
        ),
        duration_seconds=duration,
        site=str(site),
        options=options,
    )


def _build_quality_options(
    formats: list[dict[str, Any]],
    duration_seconds: int | None = None,
) -> list[QualityOption]:
    video_resolutions = [
        _short_side(item)
        for item in formats
        if item.get("vcodec") not in {None, "none"}
    ]
    max_resolution = max((value for value in video_resolutions if value), default=0)
    audio_sizes = [
        _format_size(item)
        for item in formats
        if item.get("acodec") not in {None, "none"} and item.get("vcodec") in {None, "none"}
    ]
    estimated_audio_size = max((size for size in audio_sizes if size), default=None)
    if estimated_audio_size is None and duration_seconds:
        # 按约 128 kbps 估算 MP3，最终大小仍以转码结果为准。
        estimated_audio_size = max(1, duration_seconds * 16_000)

    options = [
        QualityOption(
            preset="best",
            label="最佳画质",
            detail=f"最高 {max_resolution}p" if max_resolution else "保留来源画质",
            ext="mp4",
            height=max_resolution or None,
            filesize_bytes=_estimate_video_size(formats, None),
        )
    ]
    if max_resolution >= 1080:
        options.append(
            QualityOption(
                preset="1080p",
                label="1080p",
                detail="不超过 1080p",
                ext="mp4",
                height=1080,
                filesize_bytes=_estimate_video_size(formats, 1080),
            )
        )
    if max_resolution >= 720:
        options.append(
            QualityOption(
                preset="720p",
                label="720p",
                detail="体积更小",
                ext="mp4",
                height=720,
                filesize_bytes=_estimate_video_size(formats, 720),
            )
        )
    options.append(
        QualityOption(
            preset="audio",
            label="仅音频",
            detail="转换 MP3",
            ext="mp3",
            filesize_bytes=estimated_audio_size,
        )
    )
    return options


def _format_size(item: dict[str, Any]) -> int | None:
    value = item.get("filesize") or item.get("filesize_approx")
    return int(value) if isinstance(value, (int, float)) else None


def _short_side(item: dict[str, Any]) -> int:
    """竖屏视频按短边标记清晰度，例如 1080×1920 视为 1080p。"""
    width = _as_int(item.get("width"))
    height = _as_int(item.get("height"))
    if width and height:
        return min(width, height)
    return height or 0


def _estimate_video_size(
    formats: list[dict[str, Any]],
    resolution_limit: int | None,
) -> int | None:
    """按最高可用分辨率估算视频体积，并为音视频分离格式加上音频大小。"""
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for item in formats:
        if item.get("vcodec") in {None, "none"}:
            continue
        size = _format_size(item)
        resolution = _short_side(item)
        if not size or (resolution_limit and resolution > resolution_limit):
            continue
        candidates.append((resolution, size, item))
    if not candidates:
        return None

    _, size, selected = max(candidates, key=lambda item: (item[0], item[1]))
    if selected.get("acodec") in {None, "none"}:
        audio_size = max(
            (
                candidate_size
                for item in formats
                if item.get("acodec") not in {None, "none"}
                and item.get("vcodec") in {None, "none"}
                if (candidate_size := _format_size(item))
            ),
            default=0,
        )
        size += audio_size
    return size


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_process_error(stderr: str) -> YtDlpError:
    """把常见上游错误转成稳定错误码，避免前端依赖英文日志。"""
    normalized = stderr.lower()
    if "抖音拒绝匿名解析请求" in stderr:
        return YtDlpError("DOUYIN_CHALLENGE", "抖音风控暂时拦截，请稍后重试")
    if "drm" in normalized:
        return YtDlpError("DRM_NOT_SUPPORTED", "该内容受 DRM 保护，无法下载")
    if "private video" in normalized or "login required" in normalized:
        return YtDlpError("LOGIN_REQUIRED", "该内容需要登录，首版暂不支持")
    if "unsupported url" in normalized or "no suitable extractor" in normalized:
        return YtDlpError("UNSUPPORTED_URL", "暂不支持这个视频链接")
    if "file is larger than max-filesize" in normalized:
        return YtDlpError("FILE_TOO_LARGE", "视频文件超过大小限制")
    if "requested format is not available" in normalized:
        return YtDlpError("FORMAT_UNAVAILABLE", "所选画质已经不可用，请重新解析")
    if "ffmpeg" in normalized:
        return YtDlpError("FFMPEG_ERROR", "音视频处理失败，请确认 FFmpeg 已正确安装")
    return YtDlpError("DOWNLOAD_FAILED", "下载失败，请检查链接或稍后重试")


def _is_transient_network_error(stderr: str) -> bool:
    """只对暂时性网络故障重试，避免放大确定性错误。"""
    normalized = stderr.lower()
    hints = (
        "unexpected_eof",
        "unexpected eof",
        "ssl_error_syscall",
        "connection reset",
        "connection closed abruptly",
        "temporarily unavailable",
        "timed out",
        "http error 502",
        "http error 503",
    )
    if any(hint in normalized for hint in hints):
        return True
    return (
        "douyin" in normalized
        and ("http error 403" in normalized or "抖音拒绝匿名解析请求" in stderr)
    )


def safe_download_name(title: str, extension: str) -> str:
    """生成兼容 Windows 与移动浏览器的文件名。"""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    clean = clean[:100] or "拾帧视频"
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{clean}{ext}"

