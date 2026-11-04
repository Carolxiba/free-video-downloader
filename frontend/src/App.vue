<script setup lang="ts">
import {
  ArrowRight,
  Check,
  CircleAlert,
  Clipboard,
  Download,
  Film,
  Link2,
  LoaderCircle,
  MonitorDown,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TimerReset,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  ApiError,
  cancelDownload,
  createDownload,
  getDownload,
  inspectVideo,
} from './api'
import {
  formatBytes,
  formatDuration,
  formatEta,
  formatSpeed,
  normalizeVideoUrl,
} from './formatters'
import type { DownloadJob, Preset, VideoInfo, ViewPhase } from './types'

const url = ref('')
const phase = ref<ViewPhase>('idle')
const video = ref<VideoInfo | null>(null)
const selectedPreset = ref<Preset>('best')
const job = ref<DownloadJob | null>(null)
const errorMessage = ref('')
const inputError = ref('')
let pollTimer: ReturnType<typeof setTimeout> | undefined
let requestGeneration = 0
let autoDownloadJobId: string | null = null

const isInspecting = computed(() => phase.value === 'inspecting')
const isJobRunning = computed(() =>
  ['queued', 'downloading', 'processing'].includes(phase.value),
)
const isBusy = computed(() => isInspecting.value || isJobRunning.value)
const progress = computed(() => Math.max(0, Math.min(100, job.value?.progress ?? 0)))
const statusTitle = computed(() => {
  const titles: Record<ViewPhase, string> = {
    idle: '',
    inspecting: '正在读懂这个链接',
    inspected: '视频已经准备好了',
    queued: '已进入下载队列',
    downloading: '正在把视频带回来',
    processing: '正在拼接音视频',
    ready: '文件已准备好',
    failed: '这次没有成功',
    expired: '文件已经过期',
    cancelled: '下载已取消',
  }
  return titles[phase.value]
})

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = undefined
  }
}

function resetResult() {
  stopPolling()
  requestGeneration += 1
  phase.value = 'idle'
  video.value = null
  job.value = null
  errorMessage.value = ''
  autoDownloadJobId = null
}

function onUrlInput() {
  inputError.value = ''
  if (!isBusy.value && video.value) {
    resetResult()
  }
}

async function pasteFromClipboard() {
  inputError.value = ''
  try {
    const text = await navigator.clipboard.readText()
    if (!text.trim()) {
      inputError.value = '剪贴板里没有可用链接'
      return
    }
    url.value = text.trim()
    onUrlInput()
  } catch {
    inputError.value = '浏览器未允许读取剪贴板，请手动粘贴'
  }
}

async function inspectCurrentUrl() {
  inputError.value = ''
  errorMessage.value = ''
  stopPolling()

  let normalizedUrl: string
  try {
    normalizedUrl = normalizeVideoUrl(url.value)
  } catch (error) {
    inputError.value = error instanceof Error ? error.message : '链接格式不正确'
    return
  }

  url.value = normalizedUrl
  video.value = null
  job.value = null
  phase.value = 'inspecting'
  const generation = ++requestGeneration

  try {
    const result = await inspectVideo(normalizedUrl)
    if (generation !== requestGeneration) return
    video.value = result
    selectedPreset.value = result.options.find((option) => option.preset === 'best')?.preset
      ?? result.options[0]?.preset
      ?? 'best'
    phase.value = 'inspected'
  } catch (error) {
    if (generation !== requestGeneration) return
    errorMessage.value = readableError(error)
    phase.value = 'failed'
  }
}

async function startDownload() {
  if (!video.value || isBusy.value) return
  errorMessage.value = ''
  phase.value = 'queued'

  try {
    job.value = await createDownload(url.value, selectedPreset.value)
    applyJobState(job.value)
    schedulePoll()
  } catch (error) {
    errorMessage.value = readableError(error)
    phase.value = 'failed'
  }
}

function applyJobState(nextJob: DownloadJob) {
  job.value = nextJob
  if (nextJob.status === 'queued') phase.value = 'queued'
  if (nextJob.status === 'downloading') phase.value = 'downloading'
  if (nextJob.status === 'processing') phase.value = 'processing'
  if (nextJob.status === 'ready') {
    phase.value = 'ready'
    if (nextJob.download_url && autoDownloadJobId !== nextJob.job_id) {
      autoDownloadJobId = nextJob.job_id
      triggerLocalDownload(nextJob.download_url, nextJob.file_name)
    }
  }
  if (nextJob.status === 'failed') {
    errorMessage.value = nextJob.error || '下载失败，请稍后重试'
    phase.value = 'failed'
  }
  if (nextJob.status === 'expired') {
    errorMessage.value = nextJob.error || '文件已过期，请重新下载'
    phase.value = 'expired'
  }
  if (nextJob.status === 'cancelled') phase.value = 'cancelled'
}

function triggerLocalDownload(downloadUrl: string, fileName: string | null) {
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = fileName || ''
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function saveToDevice() {
  if (!job.value?.download_url) return
  triggerLocalDownload(job.value.download_url, job.value.file_name)
}

function schedulePoll() {
  stopPolling()
  const currentJobId = job.value?.job_id
  if (!currentJobId || !isJobRunning.value) return

  pollTimer = setTimeout(async () => {
    try {
      const nextJob = await getDownload(currentJobId)
      if (job.value?.job_id !== currentJobId) return
      applyJobState(nextJob)
      if (isJobRunning.value) schedulePoll()
    } catch (error) {
      errorMessage.value = readableError(error)
      phase.value = 'failed'
    }
  }, 700)
}

async function cancelCurrentJob() {
  const currentJobId = job.value?.job_id
  if (!currentJobId) return
  stopPolling()
  try {
    const nextJob = await cancelDownload(currentJobId)
    applyJobState(nextJob)
  } catch (error) {
    errorMessage.value = readableError(error)
    phase.value = 'failed'
  }
}

function tryAgain() {
  errorMessage.value = ''
  if (video.value) {
    phase.value = 'inspected'
    job.value = null
    return
  }
  void inspectCurrentUrl()
}

function startOver() {
  resetResult()
  url.value = ''
}

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '遇到未知错误，请稍后重试'
}

onBeforeUnmount(() => {
  stopPolling()
  requestGeneration += 1
})
</script>

<template>
  <div class="site-shell">
    <header class="site-header">
      <a class="brand" href="#top" aria-label="拾帧首页">
        <span class="brand-mark" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
        <span class="brand-name">拾帧</span>
        <span class="brand-beta">SHIZHEN</span>
      </a>

      <span class="free-pill"><span></span>免费 · 无需登录</span>
    </header>

    <main id="top">
      <section class="hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <div class="eyebrow">
            <span>PUBLIC VIDEO DOWNLOADER</span>
          </div>
          <h1 id="hero-title">
            喜欢的视频，<span>干净带走。</span>
          </h1>
          <p class="hero-lead">
            粘贴公开视频链接，选择画质后保存到手机或电脑。
          </p>
        </div>

        <div class="tool-stage">
          <section class="tool-card" aria-labelledby="tool-title">
            <div class="tool-topline">
              <span>VIDEO DOWNLOADER</span>
              <span class="status-dot">ONLINE</span>
            </div>
            <div class="tool-heading">
              <div>
                <p>解析公开、非 DRM 的视频页面</p>
                <h2 id="tool-title">粘贴视频链接</h2>
              </div>
              <Link2 :size="28" stroke-width="1.7" aria-hidden="true" />
            </div>

            <form class="url-form" novalidate @submit.prevent="inspectCurrentUrl">
              <label for="video-url">视频链接</label>
              <div class="input-shell" :class="{ 'input-shell--error': inputError }">
                <Link2 :size="20" aria-hidden="true" />
                <input
                  id="video-url"
                  v-model="url"
                  type="url"
                  inputmode="url"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="粘贴 Bilibili、YouTube 等视频链接"
                  :disabled="isBusy"
                  @input="onUrlInput"
                />
                <button
                  v-if="!isBusy"
                  class="paste-button"
                  type="button"
                  aria-label="从剪贴板粘贴"
                  @click="pasteFromClipboard"
                >
                  <Clipboard :size="17" />
                  <span>粘贴</span>
                </button>
              </div>
              <p v-if="inputError" class="field-error" role="alert">
                <CircleAlert :size="15" />{{ inputError }}
              </p>
              <p class="legal-note">
                <ShieldCheck :size="15" />
                请仅下载你拥有或已获授权的公开内容
              </p>

              <button
                v-if="phase === 'idle' || phase === 'failed' && !video"
                class="primary-button"
                type="submit"
                :disabled="isInspecting"
              >
                <LoaderCircle v-if="isInspecting" class="spin" :size="20" />
                <Sparkles v-else :size="19" />
                {{ isInspecting ? '正在解析' : '解析视频' }}
                <ArrowRight v-if="!isInspecting" :size="19" />
              </button>
            </form>

            <div class="tool-state" aria-live="polite" :aria-busy="isBusy">
              <div v-if="phase === 'inspecting'" class="loading-state">
                <div class="scan-window">
                  <LoaderCircle class="spin" :size="30" />
                  <span class="scan-line"></span>
                </div>
                <p>{{ statusTitle }}</p>
                <small>通常只需要几秒，请稍候</small>
              </div>

              <div v-else-if="video && ['inspected', 'queued', 'downloading', 'processing', 'ready', 'expired', 'cancelled'].includes(phase)" class="result-state">
                <div class="video-summary">
                  <div class="thumbnail-wrap">
                    <img
                      v-if="video.thumbnail"
                      :src="video.thumbnail"
                      :alt="`${video.title} 封面`"
                      referrerpolicy="no-referrer"
                    />
                    <div v-else class="thumbnail-placeholder">
                      <Film :size="30" />
                    </div>
                    <span class="duration-chip">{{ formatDuration(video.duration_seconds) }}</span>
                  </div>
                  <div class="video-text">
                    <span class="source-chip">{{ video.site }}</span>
                    <h3>{{ video.title }}</h3>
                    <p>{{ video.uploader || '作者未知' }}</p>
                  </div>
                </div>

                <div v-if="phase === 'inspected'" class="quality-block">
                  <div class="block-label">
                    <span>02 / QUALITY</span>
                    <span>选择保存方式</span>
                  </div>
                  <div class="quality-grid" role="radiogroup" aria-label="视频画质">
                    <button
                      v-for="option in video.options"
                      :key="option.preset"
                      class="quality-option"
                      :class="{ 'quality-option--active': selectedPreset === option.preset }"
                      type="button"
                      role="radio"
                      :aria-checked="selectedPreset === option.preset"
                      @click="selectedPreset = option.preset"
                    >
                      <span class="radio-mark">
                        <Check v-if="selectedPreset === option.preset" :size="13" />
                      </span>
                      <span class="quality-copy">
                        <strong>{{ option.label }}</strong>
                        <small>{{ option.detail }}</small>
                      </span>
                      <span class="quality-meta">
                        <strong>
                          {{ option.filesize_bytes ? `约 ${formatBytes(option.filesize_bytes)}` : '大小待定' }}
                        </strong>
                        <small>{{ option.ext.toUpperCase() }}</small>
                      </span>
                    </button>
                  </div>
                  <button class="primary-button" type="button" @click="startDownload">
                    <Download :size="19" />
                    开始下载
                    <ArrowRight :size="19" />
                  </button>
                </div>

                <div v-else-if="isJobRunning" class="progress-block">
                  <div class="progress-head">
                    <div>
                      <span>03 / DOWNLOAD</span>
                      <h4>{{ statusTitle }}</h4>
                    </div>
                    <strong>{{ Math.round(progress) }}<small>%</small></strong>
                  </div>
                  <div
                    class="progress-track"
                    role="progressbar"
                    aria-label="下载进度"
                    :aria-valuenow="Math.round(progress)"
                    aria-valuemin="0"
                    aria-valuemax="100"
                  >
                    <span :style="{ width: `${progress}%` }"></span>
                  </div>
                  <div class="progress-meta">
                    <span>{{ formatBytes(job?.downloaded_bytes ?? null) }} / {{ formatBytes(job?.total_bytes ?? null) }}</span>
                    <span>{{ formatSpeed(job?.speed_bps ?? null) }}</span>
                    <span>{{ formatEta(job?.eta_seconds ?? null) }}</span>
                  </div>
                  <p class="progress-hint">
                    {{ phase === 'queued' ? '正在等待前一个任务完成' : '生成后文件会保留 30 分钟' }}
                  </p>
                  <button class="quiet-button" type="button" @click="cancelCurrentJob">
                    <X :size="17" />取消下载
                  </button>
                </div>

                <div v-else-if="phase === 'ready' && job?.download_url" class="success-block">
                  <div class="success-icon"><Check :size="28" /></div>
                  <div>
                    <span>READY TO KEEP</span>
                    <h4>已开始下载到本地</h4>
                    <p>{{ job.file_name }} · 如果没有自动保存，请点击下方按钮</p>
                  </div>
                  <a
                    class="primary-button"
                    :href="job.download_url"
                    download
                    @click.prevent="saveToDevice"
                  >
                    <MonitorDown :size="20" />
                    重新下载
                    <ArrowRight :size="19" />
                  </a>
                  <button class="quiet-button" type="button" @click="startOver">
                    <RefreshCw :size="16" />下载另一个视频
                  </button>
                </div>

                <div v-else class="terminal-state">
                  <TimerReset :size="30" />
                  <div>
                    <h4>{{ statusTitle }}</h4>
                    <p>{{ errorMessage || '可以重新解析这个链接' }}</p>
                  </div>
                  <button class="secondary-button" type="button" @click="tryAgain">
                    再试一次
                  </button>
                </div>
              </div>

              <div v-else-if="phase === 'failed' && errorMessage" class="error-state" role="alert">
                <CircleAlert :size="26" />
                <div>
                  <strong>没有拿到视频信息</strong>
                  <p>{{ errorMessage }}</p>
                </div>
                <button class="secondary-button" type="button" @click="tryAgain">
                  重试
                </button>
              </div>

              <div v-else class="empty-state">
                <span>支持公开、非 DRM、无需登录的视频页面</span>
                <div class="empty-line"></div>
                <span>文件生成后保留 30 分钟</span>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <p>拾帧 · 仅下载本人或已获授权的公开内容</p>
      <span>Powered by yt-dlp</span>
    </footer>
  </div>
</template>

