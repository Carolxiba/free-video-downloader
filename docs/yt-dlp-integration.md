# yt-dlp 集成说明

## 上游事实

- 上游仓库：<https://github.com/yt-dlp/yt-dlp>
- 本项目固定版本：`2026.10.26`
- 上游主仓库和 PyPI 分发使用 Unlicense；打包后的 FFmpeg 发布文件可能因构建组件采用不同许可证。
- yt-dlp 支持数千个站点，但站点改动、登录、地区限制和 DRM 都可能导致解析失败。
- 完整数字媒体处理依赖 FFmpeg/FFprobe；部分站点还会要求 JavaScript 运行时。

## 封装方式

拾帧不复制或修改安装目录中的 yt-dlp 源码，而是通过参数数组启动：

```text
python -m app.ytdlp_cli --dump-single-json --skip-download --no-playlist -- URL
python -m app.ytdlp_cli --no-playlist --progress-template ... --format ... -- URL
```

这样做的原因：

- 上游安全修复和站点提取器可以独立更新。
- 参数不会经过 shell，用户输入不会被解释成命令。
- 任务队列、画质展示、文件过期和 HTTP 下载都由拾帧控制。
- 每个下载任务使用独立临时目录和固定输出文件名，避免标题进入文件系统路径。

## 质量策略

| 选项 | yt-dlp 格式选择 | 输出 |
| --- | --- | --- |
| 最佳画质 | `bv*+ba/b` | 合并后的 MP4 |
| 1080p | `bv*[height<=1080]+ba/b[height<=1080]/b` | 合并后的 MP4 |
| 720p | `bv*[height<=720]+ba/b[height<=720]/b` | 合并后的 MP4 |
| 仅音频 | `ba/b` + `--extract-audio` | MP3 |

## 升级方法

```powershell
cd backend
uv lock --upgrade-package yt-dlp
uv sync --dev
.\.venv\Scripts\python.exe -m pytest
```

升级后应重新验证至少一个公开视频解析和下载。当前依赖锁定在 `backend/uv.lock`，避免每次安装自动漂移。

## 网络和代理

如果运行环境必须先经过 HTTP(S) 出口代理，可设置：

```powershell
$env:FZ_YTDLP_PROXY = "http://127.0.0.1:7890"
```

代理只传给 yt-dlp 子进程；不要把内部代理地址写入前端或公开日志。

## 安全边界

- 不启用 `--exec`、`--compat-options allow-unsafe-ext` 等高风险选项。
- 不接收登录 Cookie，不尝试 DRM 绕过。
- 初始 URL 必须是公网 HTTP(S) 地址，并拒绝本机、私网、链路本地与保留 IP。
- 单进程同时只处理一个下载，任务和文件在当前版本中不持久化。
- 每次下载完成后再次检查文件大小；超限文件立即删除。

## 抖音兼容层

抖音网页详情接口要求 `x-secsdk-web-signature`，仅切换 UA 或传递普通 Cookie 无法稳定工作。`app/douyin_patch.py` 在官方 yt-dlp 载入后应用上游 PR #17826 的兼容逻辑：

1. 调用抖音公开注册接口取得短期游客 `ttwid`。
2. 生成一次性的临时 CSRF 值，不读取用户浏览器或登录信息。
3. 从公开页面响应取得 UIFID，并计算每次请求独立的服务端签名。
4. 附带 `aid=6383` 获取完整画质档位。
5. 为媒体 CDN 请求设置抖音 Referer，避免 `douyinvod` 返回 403。

兼容层仅覆盖 `DouyinIE` 的入口方法。待官方合并对应修复后，可删除兼容层并恢复直接使用 `python -m yt_dlp`。

