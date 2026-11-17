import type { Page } from '@playwright/test'

export const testUser = {
  id: 'user-e2e',
  username: 'e2e_reader',
  created_at: '2026-11-17T08:00:00Z',
}

export async function mockAuthenticatedUser(page: Page): Promise<void> {
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(testUser),
    }),
  )
}

export async function registerWithRealBackend(page: Page): Promise<void> {
  const username = `live_${Date.now()}_${Math.floor(Math.random() * 10_000)}`
  const password = 'safe-pass-123'
  await page.goto('/')
  if (await page.getByRole('heading', { name: '登录拾帧' }).isVisible()) {
    await page.getByRole('tab', { name: '创建账号' }).click()
    await page.getByLabel('用户名').fill(username)
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByLabel('确认密码').fill(password)
    await page.getByRole('button', { name: '创建并登录' }).click()
  }
  await page.getByRole('heading', { name: /喜欢的视频/ }).waitFor()
}
