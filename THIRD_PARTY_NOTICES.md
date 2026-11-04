# 第三方软件说明

拾帧通过包管理器使用以下开源软件，不复制其源码：

- yt-dlp：Unlicense，<https://github.com/yt-dlp/yt-dlp>
- 抖音无 Cookie 兼容层：基于 yt-dlp PR #17826 及其讨论，Unlicense，<https://github.com/yt-dlp/yt-dlp/pull/17826>
- FFmpeg：许可证取决于构建，当前验证构建为 GPL 版本
- Vue、Vite、FastAPI、Starlette、Pydantic：各自 MIT 或 BSD 许可证
- Noto Sans SC / Noto Serif SC：SIL Open Font License 1.1
- Lucide：ISC License

实际部署和再分发时应保留各依赖随包提供的许可证文本，并重新检查所选 FFmpeg 构建的分发要求。

