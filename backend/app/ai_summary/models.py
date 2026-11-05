from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


CaptionSource = Literal["author", "platform_auto"]


class SummaryStatus(StrEnum):
    QUEUED = "queued"
    FETCHING_CAPTIONS = "fetching_captions"
    SUMMARIZING = "summarizing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SummaryRequest(BaseModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def only_http_and_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("只支持 HTTP 或 HTTPS 链接")
        return value


class SummaryPoint(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    start_seconds: int = Field(ge=0)


class SummarySection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    points: list[SummaryPoint] = Field(min_length=1, max_length=20)


class SummaryContent(BaseModel):
    overview: str = Field(min_length=1, max_length=8000)
    keywords: list[str] = Field(min_length=1, max_length=15)
    sections: list[SummarySection] = Field(min_length=1, max_length=30)
    key_points: list[SummaryPoint] = Field(min_length=1, max_length=30)


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)


class SummaryResult(SummaryContent):
    transcript: list[TranscriptSegment]
    caption_source: CaptionSource
    language: str
    model: str
    created_at: datetime


class SummaryJobView(BaseModel):
    job_id: str
    status: SummaryStatus
    progress: float = Field(ge=0, le=100)
    stage: str | None = None
    result: SummaryResult | None = None
    error_code: str | None = None
    error: str | None = None
    expires_at: str


class SummaryCapabilities(BaseModel):
    configured: bool
    provider: str
    model: str
    caption_sources: list[CaptionSource]
    speech_recognition: bool = False
