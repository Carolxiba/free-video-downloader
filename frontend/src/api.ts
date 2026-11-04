import type { DownloadJob, Preset, VideoInfo } from './types'

export class ApiError extends Error {
  code: string
  status: number

  constructor(message: string, code = 'REQUEST_FAILED', status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('暂时无法连接服务，请确认后端已启动', 'NETWORK_ERROR')
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || '请求失败，请稍后重试'
    const code = typeof detail === 'object' ? detail?.code : 'REQUEST_FAILED'
    throw new ApiError(message, code, response.status)
  }

  return response.json() as Promise<T>
}

export function inspectVideo(url: string): Promise<VideoInfo> {
  return request<VideoInfo>('/api/inspect', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export function createDownload(url: string, preset: Preset): Promise<DownloadJob> {
  return request<DownloadJob>('/api/downloads', {
    method: 'POST',
    body: JSON.stringify({ url, preset }),
  })
}

export function getDownload(jobId: string): Promise<DownloadJob> {
  return request<DownloadJob>(`/api/downloads/${jobId}`)
}

export function cancelDownload(jobId: string): Promise<DownloadJob> {
  return request<DownloadJob>(`/api/downloads/${jobId}`, {
    method: 'DELETE',
  })
}

