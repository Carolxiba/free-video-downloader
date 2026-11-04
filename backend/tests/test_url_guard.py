from __future__ import annotations

import pytest

from app.url_guard import UnsafeUrlError, validate_public_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/video",
        "http://10.0.0.1/video",
        "http://192.168.1.2/video",
        "http://169.254.169.254/latest/meta-data",
        "file:///tmp/video.mp4",
        "ftp://8.8.8.8/video",
        "https://user:pass@8.8.8.8/video",
    ],
)
async def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_public_url(url)


@pytest.mark.asyncio
async def test_accepts_public_ip() -> None:
    url = "https://8.8.8.8/video"
    assert await validate_public_url(url) == url

