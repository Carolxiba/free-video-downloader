import { describe, expect, it } from 'vitest'
import {
  formatBytes,
  formatDuration,
  formatEta,
  normalizeVideoUrl,
} from '../../src/formatters'

describe('格式化与链接校验', () => {
  it('补齐空格并拒绝非 HTTP 链接', () => {
    expect(normalizeVideoUrl('  https://example.com/video  ')).toBe(
      'https://example.com/video',
    )
    expect(() => normalizeVideoUrl('file:///tmp/video.mp4')).toThrow('只支持')
    expect(() => normalizeVideoUrl('')).toThrow('先粘贴')
  })

  it('输出友好的时长、体积和预计时间', () => {
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(3725)).toBe('1:02:05')
    expect(formatBytes(1_048_576)).toBe('1.00 MB')
    expect(formatEta(125)).toBe('约 3 分钟')
  })
})

