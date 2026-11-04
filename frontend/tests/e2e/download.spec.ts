import { expect, test } from '@playwright/test'

const publicVideo = 'https://media.w3.org/2010/05/sintel/trailer.mp4'

test.describe('浏览器下载闭环', () => {
  test('解析公开视频并生成可保存文件', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium')
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname

      if (path === '/api/inspect') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            url: publicVideo,
            title: '公开测试视频',
            thumbnail: null,
            uploader: '拾帧测试',
            duration_seconds: 1,
            site: 'Test',
            options: [
              {
                preset: 'best',
                label: '最佳画质',
                detail: '保留来源画质',
                ext: 'mp4',
                height: null,
                filesize_bytes: 2268,
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
          }),
        })
        return
      }

      if (path === '/api/downloads' && request.method() === 'POST') {
        await route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: JSON.stringify({
            job_id: 'job-e2e',
            status: 'queued',
            progress: 0,
            downloaded_bytes: null,
            total_bytes: 2268,
            speed_bps: null,
            eta_seconds: null,
            file_name: null,
            error: null,
            expires_at: '2099-01-01T00:00:00Z',
            download_url: null,
          }),
        })
        return
      }

      if (path === '/api/downloads/job-e2e') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            job_id: 'job-e2e',
            status: 'ready',
            progress: 100,
            downloaded_bytes: 2268,
            total_bytes: 2268,
            speed_bps: null,
            eta_seconds: 0,
            file_name: '拾帧测试视频.mp4',
            error: null,
            expires_at: '2099-01-01T00:00:00Z',
            download_url: '/e2e-sample.mp4',
          }),
        })
        return
      }

      await route.fulfill({ status: 404, body: '{}' })
    })

    await page.goto('/')
    await page.getByRole('textbox', { name: '视频链接' }).fill(publicVideo)
    await page.getByRole('button', { name: '解析视频' }).click()

    await expect(page.getByRole('radio', { name: /最佳画质/ })).toBeVisible({
      timeout: 60_000,
    })
    await expect(page.getByText('约 2.21 KB')).toBeVisible()
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /开始下载/ }).click()

    await expect(page.getByText('已开始下载到本地')).toBeVisible({ timeout: 360_000 })
    const download = await downloadPromise

    expect(download.suggestedFilename()).toMatch(/\.mp4$/i)
    const path = await download.path()
    expect(path).toBeTruthy()
    const { stat } = await import('node:fs/promises')
    expect((await stat(path!)).size).toBeGreaterThan(1_000)
  })

  test('非法链接有清晰错误提示', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('textbox', { name: '视频链接' }).fill('这不是链接')
    await page.getByRole('button', { name: '解析视频' }).click()
    await expect(page.getByText('链接格式不正确，请粘贴完整网址')).toBeVisible()
  })
})

