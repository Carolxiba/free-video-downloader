import { ApiError } from './api'
import type { AuthUser } from './auth-types'

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      credentials: 'same-origin',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('暂时无法连接账号服务', 'NETWORK_ERROR')
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || '账号请求失败，请稍后重试'
    const code = typeof detail === 'object' ? detail?.code : 'AUTH_REQUEST_FAILED'
    throw new ApiError(message, code, response.status)
  }
  return response.json() as Promise<T>
}

export function getCurrentUser(): Promise<AuthUser> {
  return authRequest<AuthUser>('/api/auth/me')
}

export function login(username: string, password: string): Promise<AuthUser> {
  return authRequest<AuthUser>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function register(username: string, password: string): Promise<AuthUser> {
  return authRequest<AuthUser>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function logout(): Promise<void> {
  await authRequest<{ message: string }>('/api/auth/logout', {
    method: 'POST',
  })
}
