export type SummaryStatus =
  | 'queued'
  | 'fetching_captions'
  | 'summarizing'
  | 'ready'
  | 'failed'
  | 'cancelled'
  | 'expired'

export type CaptionSource = 'author' | 'platform_auto'

export interface SummaryPoint {
  text: string
  start_seconds: number
}

export interface SummarySection {
  title: string
  summary: string
  points: SummaryPoint[]
}

export interface TranscriptSegment {
  start_seconds: number
  end_seconds: number
  text: string
}

export interface SummaryResult {
  overview: string
  keywords: string[]
  sections: SummarySection[]
  key_points: SummaryPoint[]
  transcript: TranscriptSegment[]
  caption_source: CaptionSource
  language: string
  model: string
  created_at: string
}

export interface AiSummaryJob {
  job_id: string
  status: SummaryStatus
  progress: number
  stage: string | null
  result: SummaryResult | null
  error_code: string | null
  error: string | null
  expires_at: string
}

export interface AiSummaryCapabilities {
  configured: boolean
  provider: string
  model: string
  caption_sources: CaptionSource[]
  speech_recognition: boolean
}

export interface SavedSummary {
  id: string
  videoUrl: string
  videoTitle: string
  thumbnail: string | null
  durationSeconds: number | null
  savedAt: string
  result: SummaryResult
}
