"""在官方 yt-dlp 载入后应用抖音无 Cookie 兼容修复。

实现依据 yt-dlp PR #17826 及其讨论，保留独立文件便于上游合并后删除。
上游项目与本兼容层均按 Unlicense 使用。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import uuid

from yt_dlp.extractor import tiktok as tiktok_extractor
from yt_dlp.utils import ExtractorError
from yt_dlp.utils.traversal import traverse_obj


_DOUYIN = tiktok_extractor.DouyinIE
_DOUYIN._SEC_SALT = "A96D855A08C0A9707F8BEF0D9A527E4E"
_DOUYIN._REQUIRED_COOKIES = [
    "passport_csrf_token",  # 临时值即可通过服务端 Cookie 检查
    "ttwid",  # 从抖音公开注册接口获取
]
_DOUYIN._AID = 6383  # 携带该参数才能取得完整的 1080p 档位
_DOUYIN._CSRF = uuid.uuid4().hex


def _get_ttwid(self) -> str | None:
    """通过公开接口申请游客 ttwid，无需用户登录态。"""
    self._request_webpage(
        f"{self._WEBPAGE_HOST}ttwid/register",
        None,
        data=json.dumps(
            {
                "aid": self._AID,
                "service": "www.douyin.com",
            }
        ).encode(),
        headers={"content-type": "application/json"},
    )
    cookie = self._get_cookies(self._WEBPAGE_HOST).get("ttwid")
    return cookie.value if cookie else None


def _check_and_get_required_cookies(self) -> None:
    """为当前下载进程补齐抖音签名所需的匿名 Cookie。"""
    for cookie_name in self._REQUIRED_COOKIES:
        if self._get_cookies(self._WEBPAGE_HOST).get(cookie_name):
            continue
        cookie_value = (
            self._get_ttwid()
            if cookie_name == "ttwid"
            else self._CSRF
        )
        if not cookie_value:
            raise ExtractorError("无法创建抖音匿名访问会话")
        self._set_cookie(".douyin.com", cookie_name, cookie_value)


def _get_uifid(self) -> str | None:
    """优先读取 UIFID Cookie，没有时使用抖音挑战响应头。"""
    cookie_names = (
        "uifid",
        "uifid_temp",
        "uifidtemp",
        "UIFID",
        "UIFID_TEMP",
        "UIFIDTEMP",
    )
    uifid = traverse_obj(
        self._get_cookies(self._WEBPAGE_HOST),
        (cookie_names, "value"),
        get_all=False,
    )
    if uifid:
        return uifid
    response = self._request_webpage(self._WEBPAGE_HOST, None)
    return response.headers.get("x-tt-trace-host")


def _sign_query(self, query: dict) -> dict:
    """为抖音详情接口生成 x-secsdk-web-signature。"""
    uifid = self._get_uifid()
    if not uifid:
        raise ExtractorError("未能取得抖音匿名访问标识")
    timestamp = str(int(time.time()))
    signed_query = {**query, "uifid": uifid, "timestamp": timestamp}
    encoded_query = urllib.parse.urlencode(signed_query)
    signature = hashlib.md5(
        f"{uifid}_{timestamp}_{self._SEC_SALT}_{encoded_query}".encode()
    ).hexdigest()
    return {**signed_query, "x-secsdk-web-signature": signature}


def _get_aweme_detail(self, video_id: str) -> dict | None:
    """使用自动签名请求抖音视频详情。"""
    return traverse_obj(
        self._download_json(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            video_id,
            "Downloading web detail JSON",
            "Failed to download web detail JSON",
            query=self._sign_query({"aweme_id": video_id, "aid": self._AID}),
            fatal=False,
        ),
        ("aweme_detail", {dict}),
    )


def _real_extract(self, url: str) -> dict:
    """替换官方提取器入口，并补充媒体 CDN 所需 Referer。"""
    video_id = self._match_id(url)
    self._check_and_get_required_cookies()
    detail = self._get_aweme_detail(video_id)
    if not detail:
        raise ExtractorError(
            "抖音拒绝了匿名解析请求，请稍后重试",
            expected=True,
        )
    return {
        **self._parse_aweme_video_app(detail),
        "http_headers": {"Referer": self._WEBPAGE_HOST},
    }


def install_douyin_patch() -> None:
    """将兼容方法挂载到官方 DouyinIE，不复制上游其他代码。"""
    _DOUYIN._get_ttwid = _get_ttwid
    _DOUYIN._check_and_get_required_cookies = _check_and_get_required_cookies
    _DOUYIN._get_uifid = _get_uifid
    _DOUYIN._sign_query = _sign_query
    _DOUYIN._get_aweme_detail = _get_aweme_detail
    _DOUYIN._real_extract = _real_extract

