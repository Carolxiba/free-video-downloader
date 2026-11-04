"""启动 yt-dlp，并在同一进程内安装抖音兼容修复。"""

from __future__ import annotations

from yt_dlp import main

from .douyin_patch import install_douyin_patch


install_douyin_patch()

if __name__ == "__main__":
    main()

