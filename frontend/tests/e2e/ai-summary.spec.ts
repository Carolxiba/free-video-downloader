import { expect, test } from '@playwright/test'

const publicVideo = 'https://www.youtube.com/watch?v=test-video'

const summaryJob = {
  job_id: 'summary-e2e',
  status: 'ready',
  progress: 100,
  stage: '摘要已生成',
  result: {
    overview: '视频介绍了如何用结构化笔记理解一段长课程。',
    keywords: ['学习', '结构化笔记'],
    sections: [
      {
        title: '建立大纲',
        summary: '先判断内容结构，再记录细节。',
        points: [{ text: '先看章节与主题', start_seconds: 35 }],
      },
    ],
    key_points: [
      { text: '先理解整体结构', start_seconds: 35 },
      { text: '再用时间戳复盘细节', start_seconds: 95 },
    ],
    transcript: [
      { start_seconds: 1, end_seconds: 5, text: '今天我们讨论长视频学习。' },
      { start_seconds: 35, end_seconds: 42, text: '先理解整体结构。' },
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

async function mockSummaryApis(page: import('@playwright/test').Page) {
  await page.route('**/api/ai-summaries/capabilities', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        provider: 'DeepSeek',
        model: 'deepseek-flash',
        caption_sources: ['author', 'platform_auto'],
        speech_recognition: false,
      }),
    }),
  )
  await page.route('**/api/ai-summaries', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ ...summaryJob, status: 'queued', progress: 0, result: null }),
    })
  })
  await page.route('**/api/ai-summaries/summary-e2e', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summaryJob),
    }),
  )
  await page.route('**/api/inspect', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        url: publicVideo,
        title: '一段值得精读的长视频',
        thumbnail: null,
        uploader: '拾帧测试',
        duration_seconds: 600,
        site: 'Youtube',
        options: [
          {
            preset: 'best',
            label: '最佳画质',
            detail: '最高 1080p',
            ext: 'mp4',
            height: 1080,
            filesize_bytes: 8_000_000,
          },
        ],
      }),
    }),
  )
}

test('解析后生成 AI 摘要、查看全文并返回下载流程', async ({ page }, testInfo) => {
  await mockSummaryApis(page)
  await page.goto('/')
  await page.getByRole('textbox', { name: '视频链接' }).fill(publicVideo)
  await page.getByRole('button', { name: '解析视频' }).click()
  await page.getByRole('button', { name: /AI 读懂/ }).click()

  await expect(page.getByRole('dialog', { name: '一段值得精读的长视频' })).toBeVisible()
  await expect(page.getByText('视频介绍了如何用结构化笔记理解一段长课程。')).toBeVisible({
    timeout: 10_000,
  })
  await expect(page.getByText('先理解整体结构', { exact: false })).toBeVisible()
  await page.screenshot({
    path: `../.runtime/ai-summary-${testInfo.project.name}.png`,
    fullPage: true,
  })

  await page.getByRole('button', { name: '全文' }).click()
  await expect(page.getByText('今天我们讨论长视频学习。')).toBeVisible()
  await page.getByRole('button', { name: '关闭 AI 摘要' }).click()

  await expect(page.getByRole('radio', { name: /最佳画质/ })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)

  const storedCount = await page.evaluate(async () => {
    return new Promise<number>((resolve, reject) => {
      const request = indexedDB.open('shizhen-ai-summaries', 1)
      request.onerror = () => reject(request.error)
      request.onsuccess = () => {
        const database = request.result
        const transaction = database.transaction('summaries', 'readonly')
        const count = transaction.objectStore('summaries').count()
        count.onsuccess = () => {
          resolve(count.result)
          database.close()
        }
        count.onerror = () => reject(count.error)
      }
    })
  })
  expect(storedCount).toBeGreaterThanOrEqual(1)
})
