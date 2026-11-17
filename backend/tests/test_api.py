from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import DownloadRequest, QualityOption, VideoInfo
from app.ytdlp import DownloadProgress, YtDlpError


class FakeRunner:
    def __init__(self) -> None:
        self.inspect_error: YtDlpError | None = None
        self.download_error: YtDlpError | None = None

    async def inspect(self, url: str, timeout_seconds: int) -> VideoInfo:
        if self.inspect_error:
            raise self.inspect_error
        return VideoInfo(
            url=url,
            title="公开测试视频",
            thumbnail=None,
            uploader="测试作者",
            duration_seconds=10,
            site="Test",
            options=[
                QualityOption(
                    preset="best",
                    label="最佳画质",
                    detail="最高 720p",
                    ext="mp4",
                    height=720,
                ),
                QualityOption(
                    preset="audio",
                    label="仅音频",
                    detail="转换 MP3",
                    ext="mp3",
                ),
            ],
        )

    async def download(
        self,
        request: DownloadRequest,
        destination: Path,
        on_progress,
        timeout_seconds: int,
    ) -> tuple[Path, str]:
        if self.download_error:
            raise self.download_error
        destination.mkdir(parents=True, exist_ok=True)
        await on_progress(
            DownloadProgress(
                progress=55,
                downloaded_bytes=550,
                total_bytes=1000,
                speed_bps=100,
                eta_seconds=4,
            )
        )
        output = destination / f"media.{request.preset if request.preset == 'audio' else 'mp4'}"
        output.write_bytes(b"fake-video-content")
        return output, output.name


def wait_for_status(client: TestClient, job_id: str, status: str) -> dict:
    deadline = time.time() + 3
    while time.time() < deadline:
        payload = client.get(f"/api/downloads/{job_id}").json()
        if payload["status"] == status:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"任务未进入 {status} 状态")


def register_user(client: TestClient, username: str = "api_reader") -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "safe-pass-123"},
    )
    assert response.status_code == 201


def test_inspect_download_and_file(settings: Settings) -> None:
    app = create_app(settings=settings, runner=FakeRunner())
    with TestClient(app) as client:
        register_user(client)
        inspect = client.post(
            "/api/inspect",
            json={"url": "https://8.8.8.8/video"},
        )
        assert inspect.status_code == 200
        assert inspect.json()["title"] == "公开测试视频"

        created = client.post(
            "/api/downloads",
            json={"url": "https://8.8.8.8/video", "preset": "best"},
        )
        assert created.status_code == 202
        job = wait_for_status(client, created.json()["job_id"], "ready")
        assert job["download_url"].endswith("/file")

        downloaded = client.get(job["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.content == b"fake-video-content"
        assert "attachment" in downloaded.headers["content-disposition"]


def test_download_requires_prior_inspection(settings: Settings) -> None:
    app = create_app(settings=settings, runner=FakeRunner())
    with TestClient(app) as client:
        register_user(client)
        response = client.post(
            "/api/downloads",
            json={"url": "https://8.8.8.8/video", "preset": "best"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "INSPECT_REQUIRED"


def test_inspect_maps_upstream_error(settings: Settings) -> None:
    runner = FakeRunner()
    runner.inspect_error = YtDlpError("UNSUPPORTED_URL", "暂不支持这个视频链接")
    app = create_app(settings=settings, runner=runner)
    with TestClient(app) as client:
        register_user(client)
        response = client.post(
            "/api/inspect",
            json={"url": "https://8.8.8.8/video"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == {
            "code": "UNSUPPORTED_URL",
            "message": "暂不支持这个视频链接",
        }


def test_inspect_rate_limit(settings: Settings) -> None:
    app = create_app(settings=settings, runner=FakeRunner())
    with TestClient(app) as client:
        register_user(client)
        for _ in range(5):
            assert (
                client.post(
                    "/api/inspect",
                    json={"url": "https://8.8.8.8/video"},
                ).status_code
                == 200
            )
        blocked = client.post(
            "/api/inspect",
            json={"url": "https://8.8.8.8/video"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


def test_missing_job_returns_404(settings: Settings) -> None:
    app = create_app(settings=settings, runner=FakeRunner())
    with TestClient(app) as client:
        register_user(client)
        assert client.get("/api/downloads/not-found").status_code == 404


def test_health_reports_dependencies(settings: Settings) -> None:
    app = create_app(settings=settings, runner=FakeRunner())
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

