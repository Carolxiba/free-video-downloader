# AI 视频摘要

拾帧现在可以在解析视频后读取平台已有字幕，并调用 DeepSeek 生成中文学习摘要。摘要包含：

- 内容概述与关键词
- 带原视频时间戳的核心要点
- 按内容划分的章节大纲
- 完整转录
- 浏览器本地历史、复制和 Markdown 导出

## 配置

AI 摘要必须在服务端配置 DeepSeek API Key。Key 只从后端环境变量读取，不会发送到浏览器。

```powershell
$env:DEEPSEEK_API_KEY = "your-api-key"
```

修改环境变量后需要重新启动后端进程；已经运行的服务不会自动读取新的系统环境变量。

可选配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FZ_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `FZ_DEEPSEEK_MODEL` | `deepseek-flash` | 摘要模型 |
| `FZ_DEEPSEEK_TEMPERATURE` | `0.2` | 非思考模式的采样温度 |
| `FZ_DEEPSEEK_MAX_TOKENS` | `8192` | 单次摘要最大输出 token |
| `FZ_AI_REQUEST_TIMEOUT_SECONDS` | `180` | 单次 DeepSeek 请求超时 |
| `FZ_CAPTION_TIMEOUT_SECONDS` | `120` | yt-dlp 字幕请求超时 |
| `FZ_MAX_TRANSCRIPT_CHARS` | `300000` | 允许送入模型的字幕字符上限 |
| `FZ_AI_CONCURRENCY` | `1` | 同时运行的摘要任务数 |
| `BILIBILI_COOKIE` | 空 | 站点专用 B站会话字符串，仅由后端读取 |
| `BILIBILI_COOKIES_FILE` | 空 | 站点专用 Netscape Cookie 文件路径 |

## 工作方式

1. 使用独立 yt-dlp 子进程读取视频可用的作者字幕或平台自动字幕。
2. 优先选择中文作者字幕，其次中文自动字幕，再其次英文或其它语言。
3. 解析并去重 VTT、SRT 或 JSON3 字幕，保留时间戳。
4. 调用 DeepSeek `/chat/completions`，启用 JSON Output 并关闭思考模式。
5. 通过 Pydantic 校验模型结果和时间戳，再保存到浏览器 IndexedDB。

该功能没有复用或修改现有下载任务状态机。摘要任务和视频下载任务分别维护队列，失败互不影响。

## 已知限制

- 首版不做语音识别，也不会从视频音频生成字幕。
- 弹幕不会被当作字幕。
- B站字幕接口要求登录态。部署者可配置站点专用会话，客户端用户无需登录或提供 Cookie；未配置时，需要登录的字幕会返回明确提示。
- YouTube 可能要求额外的人机验证；这不属于字幕或 DeepSeek 错误。
- 服务端摘要结果只在当前进程内保留 30 分钟，浏览器本地记录最多保存最近 30 条。
- 深度模型仍可能产生遗漏或表述偏差，时间戳链接用于回到原内容核验。
