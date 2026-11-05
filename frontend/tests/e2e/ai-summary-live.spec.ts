import { expect, test } from '@playwright/test'

test('真实字幕与 DeepSeek 生成 AI 摘要', async ({ page }, testInfo) => {
  test.skip(
    process.env.RUN_LIVE_VIDEO_SUMMARY_TEST !== '1',
    '设置 RUN_LIVE_VIDEO_SUMMARY_TEST=1 才执行真实 AI 摘要浏览器测试',
  )
  test.skip(testInfo.project.name !== 'desktop-chromium')

  await page.goto('/')
  await page
    .getByRole('textbox', { name: '视频链接' })
    .fill('https://www.ted.com/talks/laura_trice_remember_to_say_thank_you')
  await page.getByRole('button', { name: '解析视频' }).click()
  await page.getByRole('button', { name: /AI 读懂/ }).click()

  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('THE SHORT VERSION')).toBeVisible({
    timeout: 120_000,
  })
  await expect(page.locator('.ai-source-stamp')).toContainText('作者字幕')
  await expect(page.locator('.ai-source-stamp')).toContainText('zh-cn')

  await page.screenshot({
    path: '../.runtime/ai-summary-live-desktop.png',
    fullPage: true,
  })
  await page.getByRole('button', { name: '关闭 AI 摘要' }).click()
  await expect(page.getByRole('radio', { name: /最佳画质/ })).toBeVisible()
})
