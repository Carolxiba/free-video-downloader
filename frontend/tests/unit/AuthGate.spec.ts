import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api'
import AuthGate from '../../src/components/AuthGate.vue'

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('../../src/auth-api', () => authMocks)

const user = {
  id: 'user-1',
  username: 'reader',
  created_at: '2026-11-17T08:00:00Z',
}

describe('AuthGate', () => {
  beforeEach(() => {
    Object.values(authMocks).forEach((mock) => mock.mockReset())
  })

  it('未登录时显示登录表单并支持注册', async () => {
    authMocks.getCurrentUser.mockRejectedValue(
      new ApiError('请先登录', 'AUTH_REQUIRED', 401),
    )
    authMocks.register.mockResolvedValue(user)
    const wrapper = mount(AuthGate, {
      slots: {
        default: '<div class="workspace">工作台</div>',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('登录拾帧')
    await wrapper.get('button[role="tab"]:nth-child(2)').trigger('click')
    await wrapper.get('#auth-username').setValue('reader')
    await wrapper.get('#auth-password').setValue('safe-pass-123')
    await wrapper.get('#auth-confirm').setValue('safe-pass-123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(authMocks.register).toHaveBeenCalledWith('reader', 'safe-pass-123')
    expect(wrapper.find('.workspace').exists()).toBe(true)
  })

  it('登录失败时保留表单并展示服务端错误', async () => {
    authMocks.getCurrentUser.mockRejectedValue(
      new ApiError('请先登录', 'AUTH_REQUIRED', 401),
    )
    authMocks.login.mockRejectedValue(
      new ApiError('用户名或密码不正确', 'INVALID_CREDENTIALS', 401),
    )
    const wrapper = mount(AuthGate)
    await flushPromises()

    await wrapper.get('#auth-username').setValue('reader')
    await wrapper.get('#auth-password').setValue('wrong-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('用户名或密码不正确')
  })

  it('已登录时渲染工作台并支持退出', async () => {
    authMocks.getCurrentUser.mockResolvedValue(user)
    authMocks.logout.mockResolvedValue(undefined)
    const wrapper = mount(AuthGate, {
      slots: {
        default: ({ logout }: { logout: () => Promise<void> }) =>
          h(
            'div',
            { class: 'workspace' },
            [h('button', { class: 'workspace-logout', onClick: logout }, '工作台')],
          ),
      },
    })
    await flushPromises()

    expect(wrapper.find('.workspace').exists()).toBe(true)
    await wrapper.get('.workspace-logout').trigger('click')
    await flushPromises()
    expect(authMocks.logout).toHaveBeenCalled()
    expect(wrapper.text()).toContain('登录拾帧')
  })

  it('接口返回 401 时回到登录页', async () => {
    authMocks.getCurrentUser.mockResolvedValue(user)
    const wrapper = mount(AuthGate, {
      slots: {
        default: '<div class="workspace">工作台</div>',
      },
    })
    await flushPromises()

    window.dispatchEvent(new Event('shizhen:auth-required'))
    await flushPromises()

    expect(wrapper.find('.workspace').exists()).toBe(false)
    expect(wrapper.text()).toContain('登录状态已过期')
  })
})
