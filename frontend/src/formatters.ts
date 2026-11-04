export function normalizeVideoUrl(rawValue: string): string {
  const value = rawValue.trim()
  if (!value) {
    throw new Error('先粘贴一个视频链接')
  }

  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error('链接格式不正确，请粘贴完整网址')
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('只支持 HTTP 或 HTTPS 链接')
  }

  return parsed.toString()
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '时长未知'
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remaining = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
  }
  return `${minutes}:${String(remaining).padStart(2, '0')}`
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null || !Number.isFinite(bytes) || bytes <= 0) return '计算中'
  const units = ['B', 'KB', 'MB', 'GB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** unitIndex
  const digits = unitIndex === 0 ? 0 : value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(digits)} ${units[unitIndex]}`
}

export function formatSpeed(bytes: number | null): string {
  return bytes && bytes > 0 ? `${formatBytes(bytes)}/s` : '正在连接'
}

export function formatEta(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '计算中'
  if (seconds < 60) return `约 ${seconds} 秒`
  const minutes = Math.ceil(seconds / 60)
  return `约 ${minutes} 分钟`
}

