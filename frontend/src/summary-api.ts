import { ApiError } from './api'
import type { AiSummaryCapabilities, AiSummaryJob } from './summary-types'

async function summaryRequest<T>(path: string, init?: RequestInit): Promise<T> {
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
    throw new ApiError('暂时无法连接 AI 摘要服务', 'NETWORK_ERROR')
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || 'AI 摘要请求失败，请稍后重试'
    const code = typeof detail === 'object' ? detail?.code : 'SUMMARY_REQUEST_FAILED'
    throw new ApiError(message, code, response.status)
  }
  return response.json() as Promise<T>
}

export function getAiSummaryCapabilities(): Promise<AiSummaryCapabilities> {
  return summaryRequest<AiSummaryCapabilities>('/api/ai-summaries/capabilities')
}

export function createAiSummary(url: string): Promise<AiSummaryJob> {
  return summaryRequest<AiSummaryJob>('/api/ai-summaries', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export function getAiSummary(jobId: string): Promise<AiSummaryJob> {
  return summaryRequest<AiSummaryJob>(`/api/ai-summaries/${jobId}`)
}

export function cancelAiSummary(jobId: string): Promise<AiSummaryJob> {
  return summaryRequest<AiSummaryJob>(`/api/ai-summaries/${jobId}`, {
    method: 'DELETE',
  })
}
