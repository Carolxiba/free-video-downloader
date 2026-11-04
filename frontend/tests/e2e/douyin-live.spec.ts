import { expect, test } from '@playwright/test'
import { stat } from 'node:fs/promises'

const douyinVideo = 'https://www.douyin.com/video/6961737553342991651'

test('抖音公开视频无需用户 Cookie 即可解析和下载', async ({ page }, testInfo) => {
  test.skip(
    process.env.RUN_LIVE_DOUYIN_TEST !== '1' ||
      testInfo.project.name !== 'desktop-chromium',
    '仅在显式开启抖音公网测试时运行',
  )

  await page.goto('/')
  await page.getByRole('textbox', { name: '视频链接' }).fill(douyinVideo)
  await page.getByRole('button', { name: '解析视频' }).click()

  await expect(page.getByRole('radio', { name: /最佳画质/ })).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.getByText('Douyin')).toBeVisible()
  await expect(page.getByRole('radio', { name: /^1080p 不超过/ })).toBeVisible()
  await expect(page.getByText('约 5.99 MB').first()).toBeVisible()
  await expect(page.getByText('约 3.89 MB').first()).toBeVisible()
  await page.screenshot({
    path: '../docs/screenshots/douyin-quality.png',
    fullPage: true,
  })
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /开始下载/ }).click()

  await expect(page.getByText('已开始下载到本地')).toBeVisible({
    timeout: 120_000,
  })
  const download = await downloadPromise
  const filePath = await download.path()
  expect(filePath).toBeTruthy()
  expect((await stat(filePath!)).size).toBeGreaterThan(100_000)
})
