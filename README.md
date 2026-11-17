# 拾帧

拾帧是一个基于 Vue 3、FastAPI 和 yt-dlp 的公开视频下载与内容摘要工具。用户注册并登录后，可以粘贴链接、解析视频信息、选择画质，或生成带时间戳的学习摘要。

当前支持单账号登录、单视频下载和 AI 摘要，不接收用户提供的来源站点 Cookie，也不处理 DRM 或播放列表。抖音解析会在服务端自动创建短期匿名访问会话。

## 项目结构

```text
.
├── backend/       # FastAPI、账号会话、任务状态机与 yt-dlp 封装
├── frontend/      # Vue 3 页面、组件测试与浏览器验收
├── docs/          # 测试与验收记录
└── scripts/       # Windows 开发环境辅助脚本
```

## 本地启动

环境要求：

- Node.js 22+
- Python 3.12
- yt-dlp 与 FFmpeg/FFprobe

首次运行可执行：

```powershell
.\scripts\setup-dev.ps1
```

如果脚本下载托管 Python 时被网络代理阻断，请从
<https://www.python.org/downloads/release/python-31210/> 安装 Python 3.12，
然后运行 `uv sync --dev --python <python.exe 路径>`。

启动后端：

```powershell
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

另开终端启动前端：

```powershell
cd frontend
npm run dev
```

浏览器访问 <http://localhost:5173>。开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8000`。

构建前端后也可以只启动 FastAPI：

```powershell
cd frontend
npm run build
cd ..\backend
uv run uvicorn app.main:app --port 8000
```

此时访问 <http://localhost:8000>。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FZ_MEDIA_ROOT` | `.runtime/downloads` | 临时下载目录 |
| `FZ_FFMPEG_DIR` | `.tools/ffmpeg` | FFmpeg 所在目录 |
| `FZ_JOB_TTL_SECONDS` | `1800` | 任务和文件保留秒数 |
| `FZ_MAX_DURATION_SECONDS` | `7200` | 单个视频最大时长 |
| `FZ_MAX_FILE_BYTES` | `1610612736` | 单个输出文件最大字节数 |
| `FZ_DOWNLOAD_TIMEOUT_SECONDS` | `900` | 下载任务超时秒数 |
| `FZ_YTDLP_PROXY` | 空 | yt-dlp 可选的 HTTP(S) 出口代理 |
| `FZ_AUTH_DB_PATH` | `.runtime/auth.db` | 用户与服务端会话数据库 |
| `FZ_AUTH_SESSION_TTL_SECONDS` | `604800` | 登录会话有效期，默认 7 天 |
| `FZ_AUTH_COOKIE_SECURE` | `false` | 生产 HTTPS 环境应设为 `true` |

## 测试

```powershell
cd backend
uv run pytest

cd ..\frontend
npm run test:unit
npm run build
npm run test:e2e
```

真实公网下载测试默认跳过，可在网络允许时显式运行：

```powershell
cd backend
$env:RUN_LIVE_VIDEO_TEST = "1"
uv run pytest tests/test_live_integration.py -q
```

抖音无 Cookie 下载测试：

```powershell
cd backend
$env:RUN_LIVE_DOUYIN_TEST = "1"
uv run pytest tests/test_live_integration.py::test_live_douyin_download_without_user_cookies -q

cd ..\frontend
$env:RUN_LIVE_DOUYIN_TEST = "1"
npx playwright test tests/e2e/douyin-live.spec.ts --project=desktop-chromium
```

## yt-dlp 边界

- 本项目只通过子进程封装 yt-dlp，不修改或复制其源码。
- 支持范围由当前 yt-dlp 提取器决定，不保证任意平台或任意链接都能成功。
- 请只下载本人拥有或已获授权的公开内容，并遵守来源平台条款。
- 当前只允许公开、非 DRM、无需来源站点登录的网页地址，不处理播放列表和直播。

详细依赖说明和验收结果见 [docs/verification.md](docs/verification.md)。

