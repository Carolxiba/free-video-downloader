<script setup lang="ts">
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Clock3,
  Copy,
  Download,
  FileText,
  History,
  LoaderCircle,
  Sparkles,
  Trash2,
  TriangleAlert,
  X,
} from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { ApiError } from '../api'
import {
  cancelAiSummary,
  createAiSummary,
  getAiSummary,
  getAiSummaryCapabilities,
} from '../summary-api'
import {
  clearSavedSummaries,
  deleteSavedSummary,
  listSavedSummaries,
  saveSummary,
} from '../summary-history'
import {
  buildSummaryMarkdown,
  downloadSummaryMarkdown,
} from '../summary-markdown'
import type {
  AiSummaryJob,
  SavedSummary,
  SummaryPoint,
  SummaryStatus,
} from '../summary-types'
import type { VideoInfo } from '../types'

const props = defineProps<{
  video: VideoInfo
}>()

type ActiveTab = 'summary' | 'transcript' | 'history'
type PanelPhase = 'idle' | 'starting' | SummaryStatus

const panelOpen = ref(false)
const panelPhase = ref<PanelPhase>('idle')
const activeTab = ref<ActiveTab>('summary')
const capabilitiesReady = ref<boolean | null>(null)
const job = ref<AiSummaryJob | null>(null)
const generatedRecord = ref<SavedSummary | null>(null)
const selectedHistoryId = ref<string | null>(null)
const history = ref<SavedSummary[]>([])
const panelError = ref('')
const actionMessage = ref('')
const closeButton = ref<HTMLButtonElement | null>(null)
const dialog = ref<HTMLElement | null>(null)

let pollTimer: ReturnType<typeof setTimeout> | undefined
let requestGeneration = 0
let savedJobId: string | null = null
let previousFocus: HTMLElement | null = null
let previousBodyOverflow = ''
let actionTimer: ReturnType<typeof setTimeout> | undefined

const isRunning = computed(() =>
  ['queued', 'fetching_captions', 'summarizing'].includes(panelPhase.value),
)
const progress = computed(() => {
  if (panelPhase.value === 'starting') return 8
  if (panelPhase.value === 'ready') return 100
  return Math.max(0, Math.min(100, job.value?.progress ?? 0))
})
const statusTitle = computed(() => {
  const titles: Record<PanelPhase, string> = {
    idle: '准备读懂这个视频',
    starting: '正在连接 DeepSeek',
    queued: '已进入摘要队列',
    fetching_captions: '正在读取平台字幕',
    summarizing: '正在整理大纲与要点',
    ready: '学习摘要已生成',
    failed: '这次没有生成',
    cancelled: '摘要已取消',
    expired: '摘要任务已过期',
  }
  return titles[panelPhase.value]
})
const selectedRecord = computed(
  () => history.value.find((record) => record.id === selectedHistoryId.value) ?? null,
)
const activeRecord = computed(() => selectedRecord.value ?? generatedRecord.value)
const sourceLabel = computed(() => {
  if (!activeRecord.value) return ''
  return activeRecord.value.result.caption_source === 'author'
    ? '作者字幕'
    : '平台自动字幕'
})

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'AI 摘要遇到未知错误，请稍后重试'
}

async function openPanel(tab: ActiveTab = 'summary') {
  activeTab.value = tab
  actionMessage.value = ''
  if (!panelOpen.value) {
    previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panelOpen.value = true
  }
  await nextTick()
  closeButton.value?.focus()
}

function closePanel() {
  panelOpen.value = false
  document.body.style.overflow = previousBodyOverflow
  previousFocus?.focus()
}

async function openHistory() {
  await openPanel('history')
  await loadHistory()
}

async function startSummary() {
  await openPanel('summary')
  selectedHistoryId.value = null
  generatedRecord.value = null
  job.value = null
  savedJobId = null
  panelError.value = ''
  actionMessage.value = ''
  panelPhase.value = 'starting'
  const generation = ++requestGeneration

  try {
    if (capabilitiesReady.value === null) {
      const capabilities = await getAiSummaryCapabilities()
      if (generation !== requestGeneration) return
      capabilitiesReady.value = capabilities.configured
      if (!capabilities.configured) {
        throw new ApiError('服务端尚未配置 DeepSeek API')
      }
    } else if (!capabilitiesReady.value) {
      throw new ApiError('服务端尚未配置 DeepSeek API')
    }

    const nextJob = await createAiSummary(props.video.url)
    if (generation !== requestGeneration) return
    job.value = nextJob
    applyJobState(nextJob)
    schedulePoll()
  } catch (error) {
    if (generation !== requestGeneration) return
    panelError.value = readableError(error)
    panelPhase.value = 'failed'
  }
}

async function applyJobState(nextJob: AiSummaryJob) {
  job.value = nextJob
  panelPhase.value = nextJob.status
  if (nextJob.status === 'ready' && nextJob.result && savedJobId !== nextJob.job_id) {
    savedJobId = nextJob.job_id
    try {
      const record = await saveSummary(props.video, nextJob)
      generatedRecord.value = record
      history.value = [
        record,
        ...history.value.filter((item) => item.id !== record.id),
      ].slice(0, 30)
      activeTab.value = 'summary'
    } catch (error) {
      generatedRecord.value = {
        id: nextJob.job_id,
        videoUrl: props.video.url,
        videoTitle: props.video.title,
        thumbnail: props.video.thumbnail,
        durationSeconds: props.video.duration_seconds,
        savedAt: new Date().toISOString(),
        result: nextJob.result,
      }
      actionMessage.value = `摘要已生成，但本地记录未保存：${readableError(error)}`
    }
  }
  if (nextJob.status === 'failed') {
    panelError.value = nextJob.error || 'AI 没有生成摘要，请稍后重试'
  }
  if (nextJob.status === 'cancelled') {
    panelError.value = nextJob.error || '摘要已取消'
  }
  if (nextJob.status === 'expired') {
    panelError.value = nextJob.error || '摘要任务已过期'
  }
}

function schedulePoll() {
  stopPolling()
  const currentJobId = job.value?.job_id
  if (!currentJobId || !isRunning.value) return
  pollTimer = setTimeout(async () => {
    try {
      const nextJob = await getAiSummary(currentJobId)
      if (job.value?.job_id !== currentJobId) return
      await applyJobState(nextJob)
      if (isRunning.value) schedulePoll()
    } catch (error) {
      panelError.value = readableError(error)
      panelPhase.value = 'failed'
    }
  }, 900)
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = undefined
  }
}

async function cancelCurrentSummary() {
  const currentJobId = job.value?.job_id
  if (!currentJobId) return
  stopPolling()
  try {
    const nextJob = await cancelAiSummary(currentJobId)
    await applyJobState(nextJob)
  } catch (error) {
    panelError.value = readableError(error)
    panelPhase.value = 'failed'
  }
}

async function loadHistory() {
  try {
    history.value = await listSavedSummaries()
  } catch (error) {
    actionMessage.value = readableError(error)
  }
}

function viewHistoryRecord(record: SavedSummary) {
  selectedHistoryId.value = record.id
  activeTab.value = 'summary'
  actionMessage.value = ''
}

async function removeHistoryRecord(record: SavedSummary) {
  try {
    await deleteSavedSummary(record.id)
    history.value = history.value.filter((item) => item.id !== record.id)
    if (selectedHistoryId.value === record.id) selectedHistoryId.value = null
    if (generatedRecord.value?.id === record.id) generatedRecord.value = null
  } catch (error) {
    actionMessage.value = readableError(error)
  }
}

async function clearHistory() {
  try {
    await clearSavedSummaries()
    history.value = []
    selectedHistoryId.value = null
    generatedRecord.value = null
  } catch (error) {
    actionMessage.value = readableError(error)
  }
}

async function copyNotes() {
  if (!activeRecord.value) return
  try {
    const markdown = buildSummaryMarkdown(activeRecord.value).split('## 全文转录')[0].trim()
    await navigator.clipboard.writeText(markdown)
    flashAction('学习笔记已复制')
  } catch {
    flashAction('浏览器未允许复制，请导出 Markdown')
  }
}

function exportNotes() {
  if (!activeRecord.value) return
  downloadSummaryMarkdown(activeRecord.value)
  flashAction('Markdown 已导出')
}

function flashAction(message: string) {
  if (actionTimer) clearTimeout(actionTimer)
  actionMessage.value = message
  actionTimer = setTimeout(() => {
    if (actionMessage.value === message) actionMessage.value = ''
  }, 2400)
}

function timestampLabel(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remaining = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
  }
  return `${minutes}:${String(remaining).padStart(2, '0')}`
}

function timestampUrl(seconds: number): string | null {
  try {
    const url = new URL(props.video.url)
    const host = url.hostname.toLowerCase()
    if (
      host.endsWith('youtube.com') ||
      host === 'youtu.be' ||
      host.endsWith('bilibili.com')
    ) {
      url.searchParams.set('t', String(Math.max(0, Math.floor(seconds))))
      return url.toString()
    }
  } catch {
    return null
  }
  return null
}

function pointHref(point: SummaryPoint): string | null {
  return timestampUrl(point.start_seconds)
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚保存'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function onDialogKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closePanel()
    return
  }
  if (event.key !== 'Tab' || !dialog.value) return
  const focusable = Array.from(
    dialog.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  )
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onBeforeUnmount(() => {
  stopPolling()
  if (actionTimer) clearTimeout(actionTimer)
  requestGeneration += 1
  document.body.style.overflow = previousBodyOverflow
})
</script>

<template>
  <div class="ai-entry">
    <div class="ai-entry-copy">
      <Sparkles :size="18" aria-hidden="true" />
      <span>
        <strong>先读懂，再决定是否保存</strong>
        <small>从平台字幕提取大纲、时间戳要点和全文</small>
      </span>
    </div>
    <div class="ai-entry-actions">
      <button class="ai-start-button" type="button" @click="startSummary">
        <BookOpen :size="17" />
        AI 读懂
        <ArrowUpRight :size="16" />
      </button>
      <button class="ai-history-button" type="button" @click="openHistory">
        <History :size="16" />
        本地记录
      </button>
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="panelOpen"
      class="ai-overlay"
      @click.self="closePanel"
    >
      <section
        ref="dialog"
        class="ai-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-panel-title"
        @keydown="onDialogKeydown"
      >
        <header class="ai-panel-header">
          <div class="ai-panel-heading">
            <span class="ai-kicker">SHIZHEN STUDY NOTE</span>
            <h2 id="ai-panel-title">{{ video.title }}</h2>
            <p>
              {{ video.uploader || '作者未知' }}
              <span v-if="activeRecord"> · {{ sourceLabel }}</span>
            </p>
          </div>
          <button
            ref="closeButton"
            class="ai-close-button"
            type="button"
            aria-label="关闭 AI 摘要"
            @click="closePanel"
          >
            <X :size="22" />
          </button>
        </header>

        <nav class="ai-tabs" aria-label="AI 摘要视图">
          <button
            type="button"
            :class="{ 'ai-tab--active': activeTab === 'summary' }"
            @click="activeTab = 'summary'"
          >
            <Sparkles :size="15" />摘要
          </button>
          <button
            type="button"
            :class="{ 'ai-tab--active': activeTab === 'transcript' }"
            :disabled="!activeRecord"
            @click="activeTab = 'transcript'"
          >
            <FileText :size="15" />全文
          </button>
          <button
            type="button"
            :class="{ 'ai-tab--active': activeTab === 'history' }"
            @click="activeTab = 'history'; loadHistory()"
          >
            <History :size="15" />本地记录
            <span v-if="history.length">{{ history.length }}</span>
          </button>
        </nav>

        <div class="ai-panel-body" aria-live="polite">
          <section v-if="activeTab === 'history'" class="ai-history-view">
            <div class="ai-history-head">
              <div>
                <span class="ai-kicker">LOCAL LIBRARY</span>
                <h3>保存在这台设备上的摘要</h3>
              </div>
              <button
                v-if="history.length"
                class="ai-text-button"
                type="button"
                @click="clearHistory"
              >
                <Trash2 :size="15" />清空全部
              </button>
            </div>

            <div v-if="history.length" class="ai-history-list">
              <article v-for="record in history" :key="record.id" class="ai-history-item">
                <button
                  class="ai-history-main"
                  type="button"
                  @click="viewHistoryRecord(record)"
                >
                  <span>{{ formatDate(record.savedAt) }}</span>
                  <strong>{{ record.videoTitle }}</strong>
                  <small>{{ record.result.overview }}</small>
                </button>
                <button
                  class="ai-icon-button"
                  type="button"
                  :aria-label="`删除 ${record.videoTitle}`"
                  @click="removeHistoryRecord(record)"
                >
                  <Trash2 :size="16" />
                </button>
              </article>
            </div>
            <div v-else class="ai-empty-state">
              <History :size="28" />
              <strong>还没有本地摘要</strong>
              <p>生成成功后会保存在当前浏览器，最多保留最近 30 条。</p>
              <button class="ai-start-button" type="button" @click="startSummary">
                <Sparkles :size="17" />生成当前视频摘要
              </button>
            </div>
          </section>

          <section v-else-if="isRunning" class="ai-progress-view">
            <div class="ai-scan-mark" aria-hidden="true">
              <span></span>
              <LoaderCircle class="ai-spin" :size="34" />
            </div>
            <span class="ai-kicker">DEEPSEEK IS READING</span>
            <h3>{{ statusTitle }}</h3>
            <p>{{ job?.stage || '请稍候，长视频可能需要更长时间' }}</p>
            <div
              class="ai-progress-track"
              role="progressbar"
              aria-label="AI 摘要进度"
              :aria-valuenow="Math.round(progress)"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span :style="{ width: `${progress}%` }"></span>
            </div>
            <small>{{ Math.round(progress) }}%</small>
            <button class="ai-text-button" type="button" @click="cancelCurrentSummary">
              <X :size="15" />取消生成
            </button>
          </section>

          <section v-else-if="panelPhase === 'failed' || panelPhase === 'cancelled' || panelPhase === 'expired'" class="ai-error-view">
            <TriangleAlert :size="30" />
            <span class="ai-kicker">{{ panelPhase.toUpperCase() }}</span>
            <h3>{{ statusTitle }}</h3>
            <p>{{ panelError || '请重新尝试生成摘要' }}</p>
            <button class="ai-start-button" type="button" @click="startSummary">
              <Sparkles :size="17" />再试一次
            </button>
          </section>

          <section
            v-else-if="activeRecord && activeTab === 'summary'"
            class="ai-note-view"
          >
            <div class="ai-note-toolbar">
              <div class="ai-source-stamp">
                <Check :size="14" />
                {{ sourceLabel }} · {{ activeRecord.result.language }} · {{ activeRecord.result.model }}
              </div>
              <div>
                <button class="ai-icon-button" type="button" aria-label="复制学习笔记" @click="copyNotes">
                  <Copy :size="17" />
                </button>
                <button class="ai-icon-button" type="button" aria-label="导出 Markdown" @click="exportNotes">
                  <Download :size="17" />
                </button>
              </div>
            </div>

            <div class="ai-overview">
              <span class="ai-kicker">THE SHORT VERSION</span>
              <p>{{ activeRecord.result.overview }}</p>
              <div class="ai-keywords">
                <span v-for="keyword in activeRecord.result.keywords" :key="keyword">
                  #{{ keyword }}
                </span>
              </div>
            </div>

            <div class="ai-timeline">
              <div class="ai-timeline-head">
                <span class="ai-kicker">KEY MOMENTS</span>
                <h3>值得回到原片的时刻</h3>
              </div>
              <article
                v-for="(point, index) in activeRecord.result.key_points"
                :key="`${point.start_seconds}-${index}`"
                class="ai-timeline-item"
              >
                <span class="ai-timeline-dot">{{ index + 1 }}</span>
                <div>
                  <component
                    :is="pointHref(point) ? 'a' : 'span'"
                    class="ai-timestamp"
                    :href="pointHref(point) || undefined"
                    :target="pointHref(point) ? '_blank' : undefined"
                    :rel="pointHref(point) ? 'noopener noreferrer' : undefined"
                  >
                    <Clock3 :size="14" />{{ timestampLabel(point.start_seconds) }}
                  </component>
                  <p>{{ point.text }}</p>
                </div>
              </article>
            </div>

            <div class="ai-sections">
              <article
                v-for="(section, index) in activeRecord.result.sections"
                :key="`${section.title}-${index}`"
                class="ai-section"
              >
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <div>
                  <h3>{{ section.title }}</h3>
                  <p>{{ section.summary }}</p>
                  <ul>
                    <li v-for="(point, pointIndex) in section.points" :key="pointIndex">
                      <component
                        :is="pointHref(point) ? 'a' : 'span'"
                        class="ai-inline-time"
                        :href="pointHref(point) || undefined"
                        :target="pointHref(point) ? '_blank' : undefined"
                        :rel="pointHref(point) ? 'noopener noreferrer' : undefined"
                      >
                        {{ timestampLabel(point.start_seconds) }}
                      </component>
                      {{ point.text }}
                    </li>
                  </ul>
                </div>
              </article>
            </div>
          </section>

          <section
            v-else-if="activeRecord && activeTab === 'transcript'"
            class="ai-transcript-view"
          >
            <div class="ai-transcript-head">
              <div>
                <span class="ai-kicker">FULL TRANSCRIPT</span>
                <h3>全文转录</h3>
              </div>
              <span>{{ activeRecord.result.transcript.length }} 段</span>
            </div>
            <div class="ai-transcript-list">
              <article
                v-for="(segment, index) in activeRecord.result.transcript"
                :key="index"
                class="ai-transcript-line"
              >
                <component
                  :is="timestampUrl(segment.start_seconds) ? 'a' : 'span'"
                  class="ai-timestamp"
                  :href="timestampUrl(segment.start_seconds) || undefined"
                  :target="timestampUrl(segment.start_seconds) ? '_blank' : undefined"
                  :rel="timestampUrl(segment.start_seconds) ? 'noopener noreferrer' : undefined"
                >
                  {{ timestampLabel(segment.start_seconds) }}
                </component>
                <p>{{ segment.text }}</p>
              </article>
            </div>
          </section>

          <section v-else class="ai-empty-state">
            <BookOpen :size="30" />
            <strong>从平台字幕开始</strong>
            <p>首版不会把弹幕当作字幕，也不会在无字幕时自行识别音频。</p>
            <button class="ai-start-button" type="button" @click="startSummary">
              <Sparkles :size="17" />生成当前视频摘要
            </button>
          </section>
        </div>

        <p v-if="actionMessage" class="ai-action-message" role="status">
          {{ actionMessage }}
        </p>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.ai-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0 0 18px;
  padding: 14px 16px;
  border: 1px solid #d8e3f2;
  border-radius: 16px;
  background:
    linear-gradient(110deg, rgb(239 246 255 / 92%), rgb(255 255 255 / 95%)),
    repeating-linear-gradient(90deg, transparent 0 18px, rgb(37 99 235 / 4%) 18px 19px);
}

.ai-entry-copy,
.ai-entry-actions,
.ai-note-toolbar,
.ai-source-stamp,
.ai-transcript-head,
.ai-history-head,
.ai-panel-heading p {
  display: flex;
  align-items: center;
}

.ai-entry-copy {
  gap: 11px;
  color: var(--blue);
  min-width: 0;
}

.ai-entry-copy span {
  display: grid;
  gap: 2px;
}

.ai-entry-copy strong {
  color: var(--ink);
  font-size: 14px;
}

.ai-entry-copy small {
  color: var(--muted);
  font-size: 12px;
}

.ai-entry-actions {
  gap: 8px;
  flex: none;
}

.ai-start-button,
.ai-history-button,
.ai-tabs button,
.ai-text-button,
.ai-icon-button,
.ai-close-button {
  border: 0;
  cursor: pointer;
}

.ai-start-button,
.ai-history-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 13px;
  border-radius: 11px;
  font-size: 13px;
  font-weight: 750;
}

.ai-start-button {
  color: white;
  background: var(--blue);
  box-shadow: 0 8px 18px rgb(37 99 235 / 20%);
}

.ai-start-button:hover {
  background: var(--blue-deep);
}

.ai-history-button {
  border: 1px solid #cad9ed;
  background: white;
  color: #355276;
}

.ai-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(15 23 42 / 54%);
  backdrop-filter: blur(8px);
}

.ai-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(1040px, 100%);
  max-height: min(920px, calc(100vh - 48px));
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 72%);
  border-radius: 24px;
  background: #fbfdff;
  box-shadow: 0 34px 90px rgb(15 23 42 / 28%);
}

.ai-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--line);
  background:
    radial-gradient(circle at 90% 0%, rgb(255 107 53 / 11%), transparent 18rem),
    white;
}

.ai-panel-heading {
  min-width: 0;
}

.ai-panel-heading h2 {
  margin: 4px 0 6px;
  overflow: hidden;
  color: var(--ink);
  font-size: clamp(19px, 3vw, 27px);
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-panel-heading p {
  gap: 4px;
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}

.ai-kicker {
  color: var(--blue);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.ai-close-button,
.ai-icon-button {
  display: inline-grid;
  place-items: center;
  background: transparent;
  color: var(--muted);
}

.ai-close-button {
  width: 40px;
  height: 40px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: white;
}

.ai-icon-button {
  width: 34px;
  height: 34px;
  border-radius: 9px;
}

.ai-close-button:hover,
.ai-icon-button:hover {
  color: var(--blue);
  background: var(--blue-soft);
}

.ai-tabs {
  display: flex;
  gap: 4px;
  padding: 9px 28px 0;
  border-bottom: 1px solid var(--line);
  background: white;
}

.ai-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 12px 13px;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}

.ai-tabs button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.ai-tabs button span {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 99px;
  background: var(--paper-deep);
  font-size: 10px;
}

.ai-tabs .ai-tab--active {
  border-color: var(--blue);
  color: var(--blue);
}

.ai-panel-body {
  min-height: 300px;
  overflow-y: auto;
  padding: 26px 28px 40px;
  scrollbar-color: #cbd5e1 transparent;
}

.ai-note-toolbar {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
}

.ai-note-toolbar > div:last-child {
  display: flex;
  gap: 4px;
}

.ai-source-stamp {
  gap: 6px;
  color: var(--green);
  font-size: 12px;
  font-weight: 650;
}

.ai-overview {
  position: relative;
  padding: 24px 26px;
  border: 1px solid #d7e4f7;
  border-radius: 18px;
  background:
    linear-gradient(135deg, #f7fbff, #ffffff 62%),
    var(--blue-soft);
}

.ai-overview::before {
  position: absolute;
  top: 22px;
  bottom: 22px;
  left: -1px;
  width: 3px;
  border-radius: 3px;
  content: "";
  background: var(--orange);
}

.ai-overview p {
  margin: 10px 0 18px;
  color: #253854;
  font-size: clamp(16px, 2vw, 19px);
  line-height: 1.85;
}

.ai-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.ai-keywords span {
  padding: 5px 9px;
  border: 1px solid #dbe6f5;
  border-radius: 99px;
  background: white;
  color: #49678c;
  font-size: 11px;
}

.ai-timeline {
  margin-top: 30px;
}

.ai-timeline-head h3,
.ai-transcript-head h3,
.ai-history-head h3 {
  margin: 4px 0 0;
  color: var(--ink);
  font-size: 20px;
}

.ai-timeline-item {
  position: relative;
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 13px;
  margin-left: 7px;
  padding: 16px 0 16px 22px;
  border-left: 1px solid #bfd2eb;
}

.ai-timeline-dot {
  position: absolute;
  top: 16px;
  left: -14px;
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border: 1px solid #c9d9ee;
  border-radius: 50%;
  background: white;
  color: var(--blue);
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 2px 8px rgb(37 99 235 / 10%);
}

.ai-timeline-item:nth-child(3n + 2) .ai-timeline-dot {
  border-color: #ffd0bd;
  color: var(--orange);
}

.ai-timestamp {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--blue);
  font-size: 11px;
  font-weight: 750;
  text-decoration: none;
}

.ai-timeline-item p {
  margin: 7px 0 0;
  color: #243550;
  font-size: 14px;
  line-height: 1.75;
}

.ai-sections {
  display: grid;
  gap: 12px;
  margin-top: 28px;
}

.ai-section {
  display: grid;
  grid-template-columns: 46px 1fr;
  gap: 15px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: white;
}

.ai-section > span {
  color: var(--orange);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  font-weight: 800;
}

.ai-section h3 {
  margin: 0 0 7px;
  font-size: 17px;
}

.ai-section p {
  margin: 0;
  color: #53647b;
  line-height: 1.7;
}

.ai-section ul {
  display: grid;
  gap: 8px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.ai-section li {
  position: relative;
  padding-left: 15px;
  color: #2d405b;
  font-size: 13px;
  line-height: 1.65;
}

.ai-section li::before {
  position: absolute;
  top: 0.65em;
  left: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  content: "";
  background: var(--blue);
}

.ai-inline-time {
  margin-right: 6px;
  color: var(--blue);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  text-decoration: none;
}

.ai-transcript-head {
  justify-content: space-between;
  margin-bottom: 16px;
}

.ai-transcript-head > span {
  color: var(--muted);
  font-size: 12px;
}

.ai-transcript-list {
  border-top: 1px solid var(--line);
}

.ai-transcript-line {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 14px;
  padding: 12px 4px;
  border-bottom: 1px solid #edf1f6;
}

.ai-transcript-line p {
  margin: 0;
  color: #2e415d;
  font-size: 14px;
  line-height: 1.72;
}

.ai-progress-view,
.ai-error-view,
.ai-empty-state {
  display: grid;
  justify-items: center;
  align-content: center;
  min-height: 350px;
  text-align: center;
}

.ai-progress-view h3,
.ai-error-view h3,
.ai-empty-state strong {
  margin: 10px 0 6px;
  color: var(--ink);
  font-size: 21px;
}

.ai-progress-view p,
.ai-error-view p,
.ai-empty-state p {
  max-width: 520px;
  margin: 0 0 18px;
  color: var(--muted);
  line-height: 1.7;
}

.ai-scan-mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 112px;
  height: 72px;
  margin-bottom: 18px;
  overflow: hidden;
  border: 1px solid #d7e4f7;
  border-radius: 15px;
  background: white;
  color: var(--blue);
}

.ai-scan-mark span {
  position: absolute;
  left: 8px;
  right: 8px;
  height: 1px;
  background: var(--orange);
  box-shadow: 0 0 9px rgb(255 107 53 / 55%);
  animation: ai-scan 1.8s ease-in-out infinite alternate;
}

.ai-progress-track {
  width: min(420px, 88%);
  height: 7px;
  overflow: hidden;
  border-radius: 99px;
  background: #e6edf7;
}

.ai-progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--blue), #63a0ff);
  transition: width 350ms ease;
}

.ai-progress-view small {
  margin: 8px 0 18px;
  color: var(--blue);
  font-weight: 750;
}

.ai-error-view > svg {
  color: var(--orange);
}

.ai-text-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 9px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
}

.ai-text-button:hover {
  color: var(--danger);
  background: #fff4f1;
}

.ai-history-head {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.ai-history-list {
  display: grid;
  gap: 9px;
}

.ai-history-item {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: white;
}

.ai-history-main {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 15px 17px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.ai-history-main span {
  color: var(--blue);
  font-size: 10px;
  font-weight: 700;
}

.ai-history-main strong {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-history-main small {
  display: -webkit-box;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.ai-action-message {
  margin: 0;
  padding: 9px 28px;
  border-top: 1px solid #ffe1d5;
  background: var(--orange-soft);
  color: #9b4526;
  font-size: 12px;
}

.ai-spin {
  animation: ai-spin 1s linear infinite;
}

@keyframes ai-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes ai-scan {
  from {
    top: 11px;
  }

  to {
    top: 58px;
  }
}

@media (max-width: 720px) {
  .ai-entry {
    align-items: flex-start;
    flex-direction: column;
  }

  .ai-entry-actions {
    width: 100%;
  }

  .ai-start-button,
  .ai-history-button {
    flex: 1;
  }

  .ai-overlay {
    align-items: end;
    padding: 0;
  }

  .ai-panel {
    width: 100%;
    height: 100dvh;
    max-height: none;
    border-width: 0;
    border-radius: 22px 22px 0 0;
  }

  .ai-panel-header {
    padding: 20px 18px 16px;
  }

  .ai-panel-heading h2 {
    white-space: normal;
  }

  .ai-tabs {
    padding-left: 14px;
    padding-right: 14px;
    overflow-x: auto;
  }

  .ai-panel-body {
    padding: 20px 18px 34px;
  }

  .ai-overview,
  .ai-section {
    padding: 18px;
  }

  .ai-transcript-line {
    grid-template-columns: 52px 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-spin,
  .ai-scan-mark span {
    animation: none;
  }
}
</style>
