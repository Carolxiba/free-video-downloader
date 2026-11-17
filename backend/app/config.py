from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_int(name: str, default: int) -> int:
    """读取正整数环境变量，非法值直接回退默认值。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _find_ffmpeg(configured_dir: Path) -> Path | None:
    """按项目本地目录和系统 PATH 的顺序查找 FFmpeg。"""
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [
        configured_dir / executable,
        configured_dir / "bin" / executable,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    media_root: Path = Path(
        os.getenv("FZ_MEDIA_ROOT", str(PROJECT_ROOT / ".runtime" / "downloads"))
    )
    ffmpeg_dir: Path = Path(
        os.getenv("FZ_FFMPEG_DIR", str(PROJECT_ROOT / ".tools" / "ffmpeg"))
    )
    job_ttl_seconds: int = _env_int("FZ_JOB_TTL_SECONDS", 1800)
    max_duration_seconds: int = _env_int("FZ_MAX_DURATION_SECONDS", 7200)
    max_file_bytes: int = _env_int("FZ_MAX_FILE_BYTES", 1_610_612_736)
    download_timeout_seconds: int = _env_int("FZ_DOWNLOAD_TIMEOUT_SECONDS", 900)
    inspect_timeout_seconds: int = _env_int("FZ_INSPECT_TIMEOUT_SECONDS", 45)
    proxy_url: str | None = (
        os.getenv("FZ_YTDLP_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or None
    )
    download_concurrency: int = 1
    inspect_rate_limit: int = 5
    inspect_rate_window_seconds: int = 60
    auth_db_path: Path = Path(
        os.getenv("FZ_AUTH_DB_PATH", str(PROJECT_ROOT / ".runtime" / "auth.db"))
    )
    auth_session_ttl_seconds: int = _env_int("FZ_AUTH_SESSION_TTL_SECONDS", 604_800)
    auth_cookie_secure: bool = _env_bool("FZ_AUTH_COOKIE_SECURE", False)

    @property
    def frontend_dist(self) -> Path:
        return self.project_root / "frontend" / "dist"

    @property
    def ffmpeg_path(self) -> Path | None:
        return _find_ffmpeg(self.ffmpeg_dir)

