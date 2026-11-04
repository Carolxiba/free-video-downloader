export type Preset = 'best' | '1080p' | '720p' | 'audio'

export type JobStatus =
  | 'queued'
  | 'downloading'
  | 'processing'
  | 'ready'
  | 'failed'
  | 'expired'
  | 'cancelled'

export interface QualityOption {
  preset: Preset
  label: string
  detail: string
  ext: string
  height: number | null
  filesize_bytes: number | null
}

export interface VideoInfo {
  url: string
  title: string
  thumbnail: string | null
  uploader: string | null
  duration_seconds: number | null
  site: string
  options: QualityOption[]
}

export interface DownloadJob {
  job_id: string
  status: JobStatus
  progress: number
  downloaded_bytes: number | null
  total_bytes: number | null
  speed_bps: number | null
  eta_seconds: number | null
  file_name: string | null
  error: string | null
  expires_at: string
  download_url: string | null
}

export type ViewPhase =
  | 'idle'
  | 'inspecting'
  | 'inspected'
  | 'queued'
  | 'downloading'
  | 'processing'
  | 'ready'
  | 'failed'
  | 'expired'
  | 'cancelled'

