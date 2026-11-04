import { expect, test } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

test('保存桌面与平板视觉验收截图', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium')
  await mkdir('../docs/screenshots', { recursive: true })

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1000 },
    { name: 'tablet', width: 768, height: 1024 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/')
    const metrics = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
    }))
    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1)
    await page.screenshot({
      path: `../docs/screenshots/${viewport.name}-hero.png`,
    })
    await page.screenshot({
      path: `../docs/screenshots/${viewport.name}.png`,
      fullPage: true,
    })
  }
})

test('保存手机视觉验收截图', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium')
  await mkdir('../docs/screenshots', { recursive: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  const inputBox = await page.getByRole('textbox', { name: '视频链接' }).boundingBox()
  const parseButtonBox = await page.getByRole('button', { name: '解析视频' }).boundingBox()
  expect(inputBox).not.toBeNull()
  expect(parseButtonBox).not.toBeNull()
  expect((inputBox?.y ?? 9999) + (inputBox?.height ?? 0)).toBeLessThan(844)
  expect((parseButtonBox?.y ?? 9999) + (parseButtonBox?.height ?? 0)).toBeLessThan(844)
  const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(documentWidth).toBeLessThanOrEqual(391)
  await page.screenshot({
    path: '../docs/screenshots/mobile-hero.png',
  })
  await page.screenshot({
    path: '../docs/screenshots/mobile.png',
    fullPage: true,
  })
})

