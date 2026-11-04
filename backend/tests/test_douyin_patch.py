from __future__ import annotations

import hashlib
from unittest.mock import patch

from app.douyin_patch import _sign_query, install_douyin_patch
from yt_dlp.extractor.tiktok import DouyinIE


class FakeDouyin:
    _SEC_SALT = "A96D855A08C0A9707F8BEF0D9A527E4E"

    def _get_uifid(self) -> str:
        return "guest-uifid"


def test_douyin_signature_contains_generated_security_fields() -> None:
    with patch("app.douyin_patch.time.time", return_value=1_700_000_000):
        result = _sign_query(FakeDouyin(), {"aweme_id": "123", "aid": 6383})  # type: ignore[arg-type]

    assert result["uifid"] == "guest-uifid"
    assert result["timestamp"] == "1700000000"
    assert len(result["x-secsdk-web-signature"]) == 32
    raw = (
        "guest-uifid_1700000000_A96D855A08C0A9707F8BEF0D9A527E4E_"
        "aweme_id=123&aid=6383&uifid=guest-uifid&timestamp=1700000000"
    )
    assert result["x-secsdk-web-signature"] == hashlib.md5(raw.encode()).hexdigest()


def test_install_patch_registers_douyin_quality_parameter() -> None:
    install_douyin_patch()
    assert DouyinIE._AID == 6383
    assert "ttwid" in DouyinIE._REQUIRED_COOKIES
    assert hasattr(DouyinIE, "_get_aweme_detail")
