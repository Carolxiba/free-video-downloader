from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


Preset = Literal["best", "1080p", "720p", "audio"]


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class QualityOption(BaseModel):
    preset: Preset
    label: str
    detail: str
    ext: str
    height: int | None = None
    filesize_bytes: int | None = None


class InspectRequest(BaseModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def only_http_and_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("只支持 HTTP 或 HTTPS 链接")
        return value


class VideoInfo(BaseModel):
    url: str
    title: str
    thumbnail: str | None = None
    uploader: str | None = None
    duration_seconds: int | None = None
    site: str
    options: list[QualityOption]


class DownloadRequest(InspectRequest):
    preset: Preset


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(ge=0, le=100)
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    file_name: str | None = None
    error: str | None = None
    expires_at: str
    download_url: str | None = None


class ApiError(BaseModel):
    code: str
    message: str


class HealthView(BaseModel):
    status: Literal["ok"]
    yt_dlp_version: str | None
    ffmpeg_available: bool
    ffmpeg_path: str | None

