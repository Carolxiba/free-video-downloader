from __future__ import annotations

from app.config import Settings
from app.ytdlp import (
    YtDlpError,
    _build_quality_options,
    _parse_progress,
    _is_transient_network_error,
    _video_info_from_payload,
    safe_download_name,
)


def test_progress_parser() -> None:
    progress = _parse_progress(
        "FZ_PROGRESS:downloading|500|1000|NA|250.5|2"
    )
    assert progress is not None
    assert progress.progress == 50
    assert progress.total_bytes == 1000
    assert progress.speed_bps == 250.5
    assert progress.eta_seconds == 2


def test_quality_options_follow_available_height() -> None:
    options = _build_quality_options(
        [
            {"height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"height": 720, "vcodec": "avc1", "acodec": "none"},
            {"height": None, "vcodec": "none", "acodec": "aac", "filesize": 8_000_000},
        ]
    )
    assert [item.preset for item in options] == ["best", "1080p", "720p", "audio"]
    assert options[-1].filesize_bytes == 8_000_000


def test_portrait_video_uses_short_side_for_quality() -> None:
    options = _build_quality_options(
        [
            {
                "width": 1080,
                "height": 1920,
                "vcodec": "h264",
                "acodec": "aac",
                "filesize": 6_000_000,
            }
        ]
    )
    assert options[0].detail == "最高 1080p"
    assert options[0].filesize_bytes == 6_000_000
    assert options[1].filesize_bytes == 6_000_000
    assert [item.preset for item in options] == ["best", "1080p", "720p", "audio"]


def test_payload_rejects_playlist_and_drm(settings: Settings) -> None:
    try:
        _video_info_from_payload({"_type": "playlist", "entries": []}, "https://8.8.8.8", settings)
    except YtDlpError as exc:
        assert exc.code == "PLAYLIST_NOT_SUPPORTED"
    else:
        raise AssertionError("播放列表应被拒绝")

    try:
        _video_info_from_payload(
            {"title": "DRM", "has_drm": True, "formats": []},
            "https://8.8.8.8",
            settings,
        )
    except YtDlpError as exc:
        assert exc.code == "DRM_NOT_SUPPORTED"
    else:
        raise AssertionError("DRM 内容应被拒绝")


def test_payload_builds_video_info(settings: Settings) -> None:
    result = _video_info_from_payload(
        {
            "title": "测试视频",
            "uploader": "测试作者",
            "duration": 65,
            "extractor_key": "Generic",
            "webpage_url": "https://8.8.8.8/video",
            "thumbnail": "https://8.8.8.8/cover.jpg",
            "formats": [{"height": 720, "vcodec": "avc1", "acodec": "none"}],
        },
        "https://8.8.8.8/video",
        settings,
    )
    assert result.title == "测试视频"
    assert result.duration_seconds == 65
    assert result.site == "Generic"


def test_safe_download_name_removes_path_characters() -> None:
    assert safe_download_name('a/b:c*?"<>|', ".mp4") == "a b c.mp4"


def test_only_transient_network_errors_are_retried() -> None:
    assert _is_transient_network_error("SSL: UNEXPECTED_EOF_WHILE_READING")
    assert _is_transient_network_error("HTTP Error 502: Bad Gateway")
    assert not _is_transient_network_error("Unsupported URL")

