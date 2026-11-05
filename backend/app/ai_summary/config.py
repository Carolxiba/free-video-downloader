from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings


@dataclass(frozen=True, slots=True)
class SummaryConfig:
    api_key: str | None = field(default=None, repr=False)
    bilibili_cookie: str | None = field(default=None, repr=False)
    bilibili_cookies_file: Path | None = field(default=None, repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    temperature: float = 0.2
    max_tokens: int = 8192
    request_timeout_seconds: int = 180
    caption_timeout_seconds: int = 120
    job_ttl_seconds: int = 1800
    max_transcript_chars: int = 300_000
    concurrency: int = 1
    root: Path = Path(".runtime/ai-summaries")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_settings(cls, settings: Settings) -> SummaryConfig:
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            bilibili_cookie=os.getenv("BILIBILI_COOKIE") or None,
            bilibili_cookies_file=(
                Path(value)
                if (value := os.getenv("BILIBILI_COOKIES_FILE"))
                else None
            ),
            base_url=(
                os.getenv("FZ_DEEPSEEK_BASE_URL")
                or os.getenv("DEEPSEEK_BASE_URL")
                or "https://api.deepseek.com"
            ).rstrip("/"),
            model=os.getenv("FZ_DEEPSEEK_MODEL", "deepseek-flash"),
            temperature=_env_float("FZ_DEEPSEEK_TEMPERATURE", 0.2),
            max_tokens=_env_int("FZ_DEEPSEEK_MAX_TOKENS", 8192),
            request_timeout_seconds=_env_int("FZ_AI_REQUEST_TIMEOUT_SECONDS", 180),
            caption_timeout_seconds=_env_int("FZ_CAPTION_TIMEOUT_SECONDS", 120),
            job_ttl_seconds=settings.job_ttl_seconds,
            max_transcript_chars=_env_int("FZ_MAX_TRANSCRIPT_CHARS", 300_000),
            concurrency=_env_int("FZ_AI_CONCURRENCY", 1),
            root=Path(
                os.getenv(
                    "FZ_AI_SUMMARY_ROOT",
                    str(settings.media_root.parent / "ai-summaries"),
                )
            ),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if 0 <= value <= 2 else default
