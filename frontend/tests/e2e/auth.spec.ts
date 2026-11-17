import { expect, test } from '@playwright/test'

test('注册、退出并重新登录', async ({ page }, testInfo) => {
  const username = `auth_${Date.now()}_${Math.floor(Math.random() * 10_000)}`
  const password = 'safe-pass-123'

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '登录拾帧' })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  await page.screenshot({
    path: `../.runtime/login-${testInfo.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('tab', { name: '创建账号' }).click()
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('确认密码').fill(password)
  await page.getByRole('button', { name: '创建并登录' }).click()

  await expect(page.getByRole('heading', { name: /喜欢的视频/ })).toBeVisible()
  await expect(page.locator('.user-copy')).toContainText(username)

  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page.getByRole('heading', { name: '登录拾帧' })).toBeVisible()

  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page.getByRole('heading', { name: /喜欢的视频/ })).toBeVisible()
})
