import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/App.vue'
import type { DownloadJob, VideoInfo } from '../../src/types'

const apiMocks = vi.hoisted(() => ({
  inspectVideo: vi.fn(),
  createDownload: vi.fn(),
  getDownload: vi.fn(),
  cancelDownload: vi.fn(),
}))

vi.mock('../../src/api', async () => {
  const actual = await vi.importActual<typeof import('../../src/api')>('../../src/api')
  return {
    ...actual,
    ...apiMocks,
  }
})

const video: VideoInfo = {
  url: 'https://example.com/video',
  title: '一段值得收藏的视频',
  thumbnail: 'https://example.com/cover.jpg',
  uploader: '拾帧测试作者',
  duration_seconds: 125,
  site: 'Example',
  options: [
    {
      preset: 'best',
      label: '最佳画质',
      detail: '最高 1080p',
      ext: 'mp4',
      height: 1080,
      filesize_bytes: 12_000_000,
    },
    {
      preset: '720p',
      label: '720p',
      detail: '体积更小',
      ext: 'mp4',
      height: 720,
      filesize_bytes: null,
    },
    {
      preset: 'audio',
      label: '仅音频',
      detail: '转换 MP3',
      ext: 'mp3',
      height: null,
      filesize_bytes: null,
    },
  ],
}

function job(overrides: Partial<DownloadJob> = {}): DownloadJob {
  return {
    job_id: 'job-123',
    status: 'queued',
    progress: 0,
    downloaded_bytes: null,
    total_bytes: null,
    speed_bps: null,
    eta_seconds: null,
    file_name: null,
    error: null,
    expires_at: '2026-11-04T12:00:00Z',
    download_url: null,
    ...overrides,
  }
}

describe('拾帧主界面', () => {
  beforeEach(() => {
    apiMocks.inspectVideo.mockReset()
    apiMocks.createDownload.mockReset()
    apiMocks.getDownload.mockReset()
    apiMocks.cancelDownload.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('首屏展示下载入口和合规提示', () => {
    const wrapper = mount(App)
    expect(wrapper.get('h1').text()).toContain('喜欢的视频')
    expect(wrapper.find('input#video-url').exists()).toBe(true)
    expect(wrapper.text()).toContain('请仅下载你拥有或已获授权的公开内容')
  })

  it('拒绝格式不正确的链接', async () => {
    const wrapper = mount(App)
    await wrapper.get('input#video-url').setValue('not-a-url')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('链接格式不正确')
    expect(apiMocks.inspectVideo).not.toHaveBeenCalled()
  })

  it('解析后渲染视频信息和可用画质', async () => {
    apiMocks.inspectVideo.mockResolvedValue(video)
    const wrapper = mount(App)
    await wrapper.get('input#video-url').setValue('https://example.com/video')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(video.title)
    expect(wrapper.text()).toContain('拾帧测试作者')
    expect(wrapper.text()).toContain('最佳画质')
    expect(wrapper.text()).toContain('仅音频')
    expect(wrapper.text()).toContain('约 11.4 MB')
    expect(wrapper.get('[role="radio"][aria-checked="true"]').text()).toContain('最佳画质')
  })

  it('选择画质后提交下载，并在轮询完成时展示保存入口', async () => {
    vi.useFakeTimers()
    apiMocks.inspectVideo.mockResolvedValue(video)
    apiMocks.createDownload.mockResolvedValue(job())
    apiMocks.getDownload
      .mockResolvedValueOnce(
        job({
          status: 'downloading',
          progress: 42,
          downloaded_bytes: 5_000_000,
          total_bytes: 12_000_000,
          speed_bps: 2_000_000,
          eta_seconds: 4,
        }),
      )
      .mockResolvedValueOnce(
        job({
          status: 'ready',
          progress: 100,
          file_name: '一段值得收藏的视频.mp4',
          download_url: '/api/downloads/job-123/file',
        }),
      )

    const wrapper = mount(App)
    await wrapper.get('input#video-url').setValue('https://example.com/video')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('[role="radio"]')[1].trigger('click')
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始下载'))!
      .trigger('click')
    await flushPromises()

    expect(apiMocks.createDownload).toHaveBeenCalledWith('https://example.com/video', '720p')

    await vi.advanceTimersByTimeAsync(700)
    await flushPromises()
    expect(wrapper.text()).toContain('正在把视频带回来')
    expect(wrapper.text()).toContain('42')

    await vi.advanceTimersByTimeAsync(700)
    await flushPromises()
    expect(wrapper.text()).toContain('已开始下载到本地')
    expect(wrapper.get('a[download]').attributes('href')).toBe('/api/downloads/job-123/file')
    expect(wrapper.get('a[download]').text()).toContain('重新下载')
  })

  it('解析失败时显示服务端错误并允许重试', async () => {
    apiMocks.inspectVideo.mockRejectedValue(new Error('暂不支持这个视频链接'))
    const wrapper = mount(App)
    await wrapper.get('input#video-url').setValue('https://example.com/video')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('暂不支持这个视频链接')
    expect(wrapper.findAll('button').some((button) => button.text().includes('重试'))).toBe(true)
  })

  it('任务过期后停止轮询并提示重新下载', async () => {
    vi.useFakeTimers()
    apiMocks.inspectVideo.mockResolvedValue(video)
    apiMocks.createDownload.mockResolvedValue(job())
    apiMocks.getDownload.mockResolvedValue(
      job({
        status: 'expired',
        error: '文件已过期，请重新下载',
      }),
    )

    const wrapper = mount(App)
    await wrapper.get('input#video-url').setValue('https://example.com/video')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('开始下载'))!
      .trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(700)
    await flushPromises()

    expect(wrapper.text()).toContain('文件已经过期')
    expect(wrapper.text()).toContain('再试一次')
  })
})

