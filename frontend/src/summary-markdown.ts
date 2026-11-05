import type { SavedSummary, SummaryPoint } from './summary-types'

function timestamp(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remaining = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
  }
  return `${minutes}:${String(remaining).padStart(2, '0')}`
}

function pointLine(point: SummaryPoint): string {
  return `- [${timestamp(point.start_seconds)}] ${point.text}`
}

export function buildSummaryMarkdown(record: SavedSummary): string {
  const { result } = record
  const lines = [
    `# ${record.videoTitle}`,
    '',
    `- 原视频：${record.videoUrl}`,
    `- 字幕来源：${result.caption_source === 'author' ? '作者字幕' : '平台自动字幕'}`,
    `- 字幕语言：${result.language}`,
    `- 生成模型：${result.model}`,
    '',
    '## 内容概述',
    '',
    result.overview,
    '',
    `关键词：${result.keywords.map((keyword) => `#${keyword}`).join(' ')}`,
    '',
    '## 核心要点',
    '',
    ...result.key_points.map(pointLine),
    '',
    '## 章节大纲',
    '',
  ]

  for (const section of result.sections) {
    lines.push(`### ${section.title}`, '', section.summary, '')
    lines.push(...section.points.map(pointLine), '')
  }

  lines.push('## 全文转录', '')
  for (const segment of result.transcript) {
    lines.push(`[${timestamp(segment.start_seconds)}] ${segment.text}`)
  }
  return `${lines.join('\n').trim()}\n`
}

export function downloadSummaryMarkdown(record: SavedSummary): void {
  const blob = new Blob([buildSummaryMarkdown(record)], {
    type: 'text/markdown;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const title = record.videoTitle
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
  link.href = url
  link.download = `${title || '拾帧视频摘要'}.md`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
