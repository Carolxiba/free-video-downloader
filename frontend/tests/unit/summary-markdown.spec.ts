import { describe, expect, it } from 'vitest'
import { buildSummaryMarkdown } from '../../src/summary-markdown'
import type { SavedSummary } from '../../src/summary-types'

describe('buildSummaryMarkdown', () => {
  it('导出概述、章节、时间戳和全文转录', () => {
    const record: SavedSummary = {
      id: 'summary-1',
      videoUrl: 'https://example.com/video',
      videoTitle: '测试课程',
      thumbnail: null,
      durationSeconds: 120,
      savedAt: '2026-11-05T08:00:00Z',
      result: {
        overview: '课程介绍核心概念。',
        keywords: ['概念', '方法'],
        sections: [
          {
            title: '第一部分',
            summary: '建立基础。',
            points: [{ text: '先理解定义', start_seconds: 12 }],
          },
        ],
        key_points: [{ text: '定义决定后续推导', start_seconds: 12 }],
        transcript: [
          { start_seconds: 12, end_seconds: 18, text: '先看定义。' },
        ],
        caption_source: 'author',
        language: 'zh-CN',
        model: 'deepseek-flash',
        created_at: '2026-11-05T08:00:00Z',
      },
    }

    const markdown = buildSummaryMarkdown(record)

    expect(markdown).toContain('# 测试课程')
    expect(markdown).toContain('## 核心要点')
    expect(markdown).toContain('- [0:12] 定义决定后续推导')
    expect(markdown).toContain('### 第一部分')
    expect(markdown).toContain('[0:12] 先看定义。')
  })
})
