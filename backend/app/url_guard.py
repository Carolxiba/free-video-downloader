from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """URL 不符合公网访问约束。"""


async def validate_public_url(raw_url: str) -> str:
    """限制为公网 HTTP(S) URL，避免把服务端当作内网探测代理。"""
    if len(raw_url) > 2048:
        raise UnsafeUrlError("链接过长")

    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("只支持 HTTP 或 HTTPS 链接")
    if not parsed.hostname:
        raise UnsafeUrlError("链接缺少有效域名")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("链接不能包含用户名或密码")

    host = parsed.hostname.rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        _ensure_global_ip(literal)
    else:
        try:
            results = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise UnsafeUrlError("无法解析链接域名") from exc

        if not results:
            raise UnsafeUrlError("无法解析链接域名")
        for result in results:
            address = result[4][0]
            try:
                _ensure_global_ip(ipaddress.ip_address(address))
            except ValueError as exc:
                raise UnsafeUrlError("链接域名指向了不安全地址") from exc

    return raw_url


def _ensure_global_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """只允许公网 IP，显式拒绝本机、私网、链路本地和保留地址。"""
    if not address.is_global:
        raise UnsafeUrlError("不支持本机、内网或保留地址")

