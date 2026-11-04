# 拾帧验收记录

验收日期：2026-11-04

## 环境

| 组件 | 实际版本 |
| --- | --- |
| Node.js | 24.14.1 |
| npm | 11.11.0 |
| Python | 3.12.10 |
| yt-dlp | 2026.10.26 |
| FFmpeg / FFprobe | 9.0.2 essentials build |
| 浏览器 | Microsoft Edge（Playwright `channel: msedge`） |

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 后端 Pytest | 26 项通过，2 项公网测试按配置跳过 |
| 前端 Vitest | 8 项通过 |
| Vue TypeScript + Vite 生产构建 | 通过 |
| Playwright 浏览器测试 | 5 项通过，5 项按设备/公网测试开关跳过 |
| npm 安全审计 | 0 个已知漏洞 |
| Python 编译检查 | 通过 |

后端测试覆盖 URL 安全、播放列表/DRM 拒绝、画质映射、任务状态、并发限制、取消、过期清理、文件下载、限流和错误映射。前端测试覆盖输入校验、解析、画质选择、下载轮询、成功保存、解析失败、过期状态和格式化函数。

## 抖音无 Cookie 验证

测试视频：

```text
https://www.douyin.com/video/6961737553342991651
```

- 用户未提供任何 Cookie，服务端自动创建临时游客会话和请求签名。
- 解析结果包含标题、19 秒时长以及 `best`、`1080p`、`720p`、`audio` 选项。
- 画质选项展示预估文件大小，竖屏 1080×1920 正确显示为 1080p。
- 下载任务成功完成，文件大小为 6,281,768 字节。
- FFprobe 确认为 H.264、1080×1920、19.733333 秒的 MP4。
- 通过真实 Edge 浏览器完成“粘贴链接 → 解析 → 自动保存文件”全流程测试，下载完成后无需再次点击保存。

## 真实公网下载

测试样本：

```text
https://media.w3.org/2010/05/sintel/trailer.mp4
```

实际执行结果：

- yt-dlp 成功解析标题 `trailer` 和 `Generic` 来源。
- 后端任务依次进入 `queued`、`downloading`、`ready`。
- 下载文件大小为 4,372,373 字节。
- FFprobe 识别为 `mov,mp4,m4a,3gp,3g2,mj2`，时长 52.208333 秒。
- 保存到设备后文件与后端任务输出大小一致。

本机网络对 Python 的公共 HTTPS 请求存在间歇性 `SSL: UNEXPECTED_EOF_WHILE_READING` 拦截，因此默认可重复的浏览器 E2E 使用固定 API 响应和 1 秒本地 MP4，避免测试随机波动。公网真实链路可以用以下命令重新验证：

```powershell
cd backend
$env:RUN_LIVE_VIDEO_TEST = "1"
uv run pytest tests/test_live_integration.py -q
```

如环境经代理出网，请同时配置 `FZ_YTDLP_PROXY`。

## 浏览器验收

- 桌面：1440 × 1000
- 平板：768 × 1024
- 手机：390 × 844，设备像素比 3
- 三个视口均通过横向溢出断言。
- 手机首屏中的链接输入框和“解析视频”按钮完整可见。
- 浏览器完成解析、画质展示、轮询、成功状态和文件下载。

截图：

- [桌面](screenshots/desktop.png)
- [平板](screenshots/tablet.png)
- [手机](screenshots/mobile.png)
- [抖音画质与文件大小](screenshots/douyin-quality.png)

## 当前限制

- 任务保存在 Uvicorn 单进程内存中，服务重启后任务失效。
- 同时只运行一个下载；多实例横向扩展需要共享队列和对象存储。
- 不支持播放列表、直播、需要登录 Cookie、DRM 或付费访问控制。
- 平台支持能力取决于固定版本的 yt-dlp，不承诺所有来源成功。
- 文件名和错误提示已做安全处理，但正式公网运营仍应补充更强限流、日志脱敏、监控与法律审查。

