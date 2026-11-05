# AI 视频摘要验收记录

验收日期：2026-11-05

## 自动化测试

| 检查 | 结果 |
| --- | --- |
| 后端 Pytest | 53 项通过，5 项可选公网测试跳过 |
| Python 编译检查 | 通过 |
| 前端 Vitest | 12 项通过 |
| Vue TypeScript + Vite 生产构建 | 通过 |
| Playwright | 7 项通过，7 项按设备、公网或实时测试开关跳过 |
| uv 锁文件离线一致性检查 | 通过 |

新增测试覆盖字幕优先级、VTT/SRT/JSON3 解析、自动字幕去重、弹幕排除、DeepSeek 请求结构、JSON 校验、时间戳越界、错误码映射、任务成功/取消/过期清理、无字幕提示、本地历史、Markdown 导出，以及桌面和移动端摘要阅读流程。

浏览器验收使用真实 Microsoft Edge，通过固定 API 响应验证：

1. 粘贴链接并解析视频。
2. 点击“AI 读懂”打开阅读面板。
3. 展示概述、关键词、带时间戳的要点和章节。
4. 切换全文转录。
5. 关闭面板后，原画质选择和下载入口仍可继续使用。
6. 摘要成功写入浏览器 IndexedDB。
7. 桌面与手机视口均无横向溢出。

## DeepSeek 实时检查

已使用 Machine 级环境变量中的有效 `DEEPSEEK_API_KEY` 完成两项真实测试：

- DeepSeek 文本摘要请求通过，返回内容通过 Pydantic 与时间戳校验。
- TED 公开视频的 `zh-cn` 字幕成功获取并送入 DeepSeek，完整生成概述、章节和带时间戳要点。

另一次 API 端到端测试成功覆盖“创建摘要任务 → yt-dlp 获取字幕 → DeepSeek 生成摘要 → 轮询得到 ready 结果”的完整流程。

真实浏览器测试也已完成：在 Microsoft Edge 中解析 TED 视频，获取 `zh-cn` 作者字幕，调用 DeepSeek 渲染摘要，并确认关闭阅读面板后仍可继续使用下载流程。

复现命令：

```powershell
cd backend
$env:RUN_LIVE_DEEPSEEK_TEST = "1"
$env:RUN_LIVE_VIDEO_SUMMARY_TEST = "1"
uv run pytest tests/test_ai_live_integration.py -q
```

## 字幕来源限制

对多个公开 B站样例执行了只读字幕检查，匿名 yt-dlp 只返回 `danmaku` 弹幕，没有作者 CC 或自动字幕。根据当前 yt-dlp 的 B站提取器行为，部分 CC 字幕需要来源站点登录。本项目不接收用户 Cookie，也不把弹幕作为摘要输入，因此这类视频会明确提示“没有可用字幕”。
