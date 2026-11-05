import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VideoSummaryLauncher from '../../src/components/VideoSummaryLauncher.vue'
import type { AiSummaryJob, SavedSummary } from '../../src/summary-types'
import type { VideoInfo } from '../../src/types'

const apiMocks = vi.hoisted(() => ({
  getAiSummaryCapabilities: vi.fn(),
  createAiSummary: vi.fn(),
  getAiSummary: vi.fn(),
  cancelAiSummary: vi.fn(),
}))
const historyMocks = vi.hoisted(() => ({
  saveSummary: vi.fn(),
  listSavedSummaries: vi.fn(),
  deleteSavedSummary: vi.fn(),
  clearSavedSummaries: vi.fn(),
}))
const markdownMocks = vi.hoisted(() => ({
  buildSummaryMarkdown: vi.fn(),
  downloadSummaryMarkdown: vi.fn(),
}))

vi.mock('../../src/summary-api', () => apiMocks)
vi.mock('../../src/summary-history', () => historyMocks)
vi.mock('../../src/summary-markdown', () => markdownMocks)

const video: VideoInfo = {
  url: 'https://www.youtube.com/watch?v=abc',
  title: '如何真正理解反向传播',
  thumbnail: null,
  uploader: '拾帧测试作者',
  duration_seconds: 320,
  site: 'Youtube',
  options: [],
}

function readyJob(): AiSummaryJob {
  return {
    job_id: 'summary-1',
    status: 'ready',
    progress: 100,
    stage: '摘要已生成',
    result: {
      overview: '这段视频解释了反向传播和链式法则。',
      keywords: ['反向传播', '链式法则'],
      sections: [
        {
          title: '计算梯度',
          summary: '通过链式法则逐步计算梯度。',
          points: [{ text: '从输出层向输入层传播', start_seconds: 35 }],
        },
      ],
      key_points: [
        { text: '理解链式法则是关键', start_seconds: 35 },
        { text: '检查每一步的梯度维度', start_seconds: 95 },
      ],
      transcript: [
        { start_seconds: 1, end_seconds: 4, text: '今天介绍反向传播。' },
        { start_seconds: 35, end_seconds: 41, text: '核心是链式法则。' },
      ],
      caption_source: 'author',
      language: 'zh-CN',
      model: 'deepseek-flash',
      created_at: '2026-11-05T08:00:00Z',
    },
    error_code: null,
    error: null,
    expires_at: '2026-11-05T08:30:00Z',
  }
}

function savedRecord(job: AiSummaryJob): SavedSummary {
  return {
    id: job.job_id,
    videoUrl: video.url,
    videoTitle: video.title,
    thumbnail: video.thumbnail,
    durationSeconds: video.duration_seconds,
    savedAt: '2026-11-05T08:01:00Z',
    result: job.result!,
  }
}

describe('VideoSummaryLauncher', () => {
  beforeEach(() => {
    apiMocks.getAiSummaryCapabilities.mockReset()
    apiMocks.createAiSummary.mockReset()
    apiMocks.getAiSummary.mockReset()
    apiMocks.cancelAiSummary.mockReset()
    historyMocks.saveSummary.mockReset()
    historyMocks.listSavedSummaries.mockReset()
    historyMocks.deleteSavedSummary.mockReset()
    historyMocks.clearSavedSummaries.mockReset()
    markdownMocks.buildSummaryMarkdown.mockReset()
    markdownMocks.downloadSummaryMarkdown.mockReset()
    apiMocks.getAiSummaryCapabilities.mockResolvedValue({
      configured: true,
      provider: 'DeepSeek',
      model: 'deepseek-flash',
      caption_sources: ['author', 'platform_auto'],
      speech_recognition: false,
    })
    historyMocks.listSavedSummaries.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
    document.body.style.overflow = ''
  })

  it('从视频卡片启动摘要并渲染时间戳、转录和历史记录', async () => {
    vi.useFakeTimers()
    const job = readyJob()
    apiMocks.createAiSummary.mockResolvedValue({
      ...job,
      status: 'queued',
      progress: 0,
      result: null,
    })
    apiMocks.getAiSummary.mockResolvedValue(job)
    historyMocks.saveSummary.mockResolvedValue(savedRecord(job))
    markdownMocks.buildSummaryMarkdown.mockReturnValue('# 摘要\n\n## 全文转录\n\n字幕')

    const wrapper = mount(VideoSummaryLauncher, {
      props: { video },
      attachTo: document.body,
    })
    expect(wrapper.text()).toContain('AI 读懂')

    await wrapper.get('button.ai-start-button').trigger('click')
    await flushPromises()
    expect(apiMocks.createAiSummary).toHaveBeenCalledWith(video.url)

    await vi.advanceTimersByTimeAsync(900)
    await flushPromises()

    expect(document.body.textContent).toContain('这段视频解释了反向传播')
    expect(document.body.textContent).toContain('理解链式法则是关键')
    expect(document.body.querySelector('.ai-timestamp')?.textContent).toContain('0:35')
    expect(historyMocks.saveSummary).toHaveBeenCalledWith(video, job)

    const transcriptTab = Array.from(document.querySelectorAll<HTMLButtonElement>('.ai-tabs button'))
      .find((button) => button.textContent?.includes('全文'))
    transcriptTab?.click()
    await flushPromises()
    expect(document.body.textContent).toContain('今天介绍反向传播')

    wrapper.unmount()
  })

  it('把无字幕错误限制在摘要面板内', async () => {
    vi.useFakeTimers()
    apiMocks.createAiSummary.mockResolvedValue({
      ...readyJob(),
      status: 'queued',
      result: null,
    })
    apiMocks.getAiSummary.mockResolvedValue({
      ...readyJob(),
      status: 'failed',
      result: null,
      error_code: 'CAPTIONS_NOT_FOUND',
      error: '该视频没有可读取的作者字幕或平台自动字幕',
    })

    const wrapper = mount(VideoSummaryLauncher, {
      props: { video },
      attachTo: document.body,
    })
    await wrapper.get('button.ai-start-button').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(900)
    await flushPromises()

    expect(document.body.textContent).toContain('该视频没有可读取的作者字幕')
    expect(document.body.textContent).toContain('再试一次')

    wrapper.unmount()
  })

  it('可以打开本地记录且只有用户点击时才请求摘要', async () => {
    const job = readyJob()
    historyMocks.listSavedSummaries.mockResolvedValue([savedRecord(job)])
    const wrapper = mount(VideoSummaryLauncher, {
      props: { video },
      attachTo: document.body,
    })

    expect(apiMocks.getAiSummaryCapabilities).not.toHaveBeenCalled()
    await wrapper.get('button.ai-history-button').trigger('click')
    await flushPromises()

    expect(historyMocks.listSavedSummaries).toHaveBeenCalled()
    expect(document.body.textContent).toContain('如何真正理解反向传播')
    expect(apiMocks.createAiSummary).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
