from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        media_root=tmp_path / "downloads",
        ffmpeg_dir=tmp_path / "ffmpeg",
        job_ttl_seconds=2,
        max_duration_seconds=7200,
        max_file_bytes=10_000_000,
        download_timeout_seconds=30,
        inspect_timeout_seconds=5,
        proxy_url=None,
        auth_db_path=tmp_path / "auth.db",
        auth_session_ttl_seconds=3600,
        auth_cookie_secure=False,
    )

