<script setup lang="ts">
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  UserRound,
} from '@lucide/vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError } from '../api'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '../auth-api'
import type { AuthUser } from '../auth-types'

type AuthMode = 'login' | 'register'

const user = ref<AuthUser | null>(null)
const loading = ref(true)
const submitting = ref(false)
const mode = ref<AuthMode>('login')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const errorMessage = ref('')

onMounted(async () => {
  window.addEventListener('shizhen:auth-required', handleAuthRequired)
  try {
    user.value = await getCurrentUser()
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      errorMessage.value = readableError(error)
    }
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('shizhen:auth-required', handleAuthRequired)
})

function handleAuthRequired() {
  user.value = null
  loading.value = false
  mode.value = 'login'
  errorMessage.value = '登录状态已过期，请重新登录'
}

function switchMode(nextMode: AuthMode) {
  mode.value = nextMode
  confirmPassword.value = ''
  errorMessage.value = ''
}

async function submit() {
  errorMessage.value = ''
  if (!username.value.trim()) {
    errorMessage.value = '请输入用户名'
    return
  }
  if (password.value.length < 8) {
    errorMessage.value = '密码至少需要 8 位'
    return
  }
  if (mode.value === 'register' && password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  submitting.value = true
  try {
    user.value =
      mode.value === 'login'
        ? await loginRequest(username.value.trim(), password.value)
        : await registerRequest(username.value.trim(), password.value)
    password.value = ''
    confirmPassword.value = ''
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    submitting.value = false
  }
}

async function logout() {
  try {
    await logoutRequest()
  } finally {
    user.value = null
    mode.value = 'login'
    username.value = ''
    password.value = ''
    confirmPassword.value = ''
    errorMessage.value = ''
  }
}

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '账号操作失败，请稍后重试'
}
</script>

<template>
  <div v-if="loading" class="auth-loading" aria-live="polite">
    <LoaderCircle class="auth-spin" :size="30" />
    <span>正在确认登录状态</span>
  </div>

  <slot v-else-if="user" :user="user" :logout="logout" />

  <main v-else class="auth-shell">
    <section class="auth-story">
      <a class="auth-brand" href="#" aria-label="拾帧首页">
        <span class="auth-brand-mark" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
        <span>拾帧</span>
        <small>SHIZHEN</small>
      </a>
      <div>
        <span class="auth-kicker">YOUR VIDEO KNOWLEDGE DESK</span>
        <h1>登录之后，<br /><em>视频和笔记都只属于你。</em></h1>
        <p>
          解析链接、保存视频、生成带时间戳的摘要。任务和内容按账号隔离，
          不再混在一起。
        </p>
      </div>
      <div class="auth-points">
        <span><ShieldCheck :size="16" />密码使用不可逆哈希保存</span>
        <span><LockKeyhole :size="16" />登录会话仅保存在 HttpOnly Cookie</span>
      </div>
    </section>

    <section class="auth-card" aria-labelledby="auth-title">
      <div class="auth-card-heading">
        <span class="auth-icon"><UserRound :size="22" /></span>
        <div>
          <small>{{ mode === 'login' ? 'WELCOME BACK' : 'CREATE ACCOUNT' }}</small>
          <h2 id="auth-title">{{ mode === 'login' ? '登录拾帧' : '创建拾帧账号' }}</h2>
        </div>
      </div>

      <div class="auth-tabs" role="tablist" aria-label="账号操作">
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'login'"
          :class="{ active: mode === 'login' }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'register'"
          :class="{ active: mode === 'register' }"
          @click="switchMode('register')"
        >
          创建账号
        </button>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label for="auth-username">用户名</label>
        <div class="auth-input">
          <UserRound :size="17" />
          <input
            id="auth-username"
            v-model="username"
            autocomplete="username"
            maxlength="32"
            placeholder="3-32 位用户名"
          />
        </div>

        <label for="auth-password">密码</label>
        <div class="auth-input">
          <LockKeyhole :size="17" />
          <input
            id="auth-password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            maxlength="128"
            placeholder="至少 8 位"
          />
          <button
            class="auth-eye"
            type="button"
            :aria-label="showPassword ? '隐藏密码' : '显示密码'"
            @click="showPassword = !showPassword"
          >
            <EyeOff v-if="showPassword" :size="17" />
            <Eye v-else :size="17" />
          </button>
        </div>

        <template v-if="mode === 'register'">
          <label for="auth-confirm">确认密码</label>
          <div class="auth-input">
            <LockKeyhole :size="17" />
            <input
              id="auth-confirm"
              v-model="confirmPassword"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="new-password"
              maxlength="128"
              placeholder="再次输入密码"
            />
          </div>
        </template>

        <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>

        <button class="auth-submit" type="submit" :disabled="submitting">
          <LoaderCircle v-if="submitting" class="auth-spin" :size="18" />
          <Sparkles v-else :size="18" />
          {{ submitting ? '正在处理' : mode === 'login' ? '进入工作台' : '创建并登录' }}
          <ArrowRight v-if="!submitting" :size="18" />
        </button>
      </form>

      <p class="auth-footnote">
        登录即表示你同意仅处理本人拥有或已获授权的公开视频内容。
      </p>
    </section>
  </main>
</template>

<style scoped>
.auth-loading {
  min-height: 100vh;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--muted);
  background: var(--paper);
  font-size: 13px;
}

.auth-shell {
  min-height: 100vh;
  padding: clamp(22px, 5vw, 70px);
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(380px, 0.8fr);
  align-items: center;
  gap: clamp(40px, 8vw, 120px);
  background:
    linear-gradient(125deg, rgb(239 246 255 / 90%), transparent 42%),
    radial-gradient(circle at 8% 90%, rgb(255 107 53 / 10%), transparent 27rem),
    #f8fafc;
}

.auth-story {
  min-height: min(680px, 82vh);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.auth-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: max-content;
  font-size: 22px;
  font-weight: 850;
  letter-spacing: 0.08em;
}

.auth-brand small {
  color: var(--muted);
  font-size: 9px;
  letter-spacing: 0.18em;
  writing-mode: vertical-rl;
}

.auth-brand-mark {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border-radius: 50%;
  background: var(--blue);
  transform: rotate(-4deg);
}

.auth-brand-mark span {
  width: 4px;
  height: 15px;
  border-radius: 2px;
  background: white;
}

.auth-brand-mark span:nth-child(2) {
  height: 22px;
  background: var(--orange);
}

.auth-kicker {
  color: var(--blue);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.auth-story h1 {
  max-width: 760px;
  margin: 20px 0 0;
  font-size: clamp(48px, 6vw, 86px);
  line-height: 1.04;
  letter-spacing: -0.075em;
}

.auth-story h1 em {
  color: var(--blue);
  font-style: normal;
}

.auth-story p {
  max-width: 560px;
  margin: 28px 0 0;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.9;
}

.auth-points {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 22px;
  color: #52627a;
  font-size: 11px;
}

.auth-points span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.auth-points svg {
  color: var(--green);
}

.auth-card {
  width: 100%;
  max-width: 470px;
  justify-self: end;
  padding: clamp(26px, 4vw, 42px);
  border: 1px solid rgb(255 255 255 / 78%);
  border-radius: 26px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 34px 80px rgb(15 23 42 / 12%);
  backdrop-filter: blur(18px);
}

.auth-card-heading {
  display: flex;
  align-items: center;
  gap: 13px;
}

.auth-card-heading small {
  color: var(--muted);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.14em;
}

.auth-card-heading h2 {
  margin: 3px 0 0;
  font-size: 26px;
}

.auth-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 15px;
  background: var(--blue-soft);
  color: var(--blue);
}

.auth-tabs {
  margin: 28px 0 24px;
  padding: 4px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-radius: 12px;
  background: var(--paper-deep);
}

.auth-tabs button {
  min-height: 40px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.auth-tabs button.active {
  background: white;
  color: var(--blue);
  box-shadow: 0 3px 12px rgb(15 23 42 / 8%);
}

.auth-form {
  display: grid;
  gap: 9px;
}

.auth-form label {
  margin-top: 7px;
  color: #394b63;
  font-size: 12px;
  font-weight: 700;
}

.auth-input {
  min-height: 50px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbfdff;
  color: #8291a5;
}

.auth-input:focus-within {
  border-color: rgb(37 99 235 / 55%);
  box-shadow: 0 0 0 4px rgb(37 99 235 / 8%);
}

.auth-input input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  font-size: 14px;
}

.auth-eye {
  display: grid;
  place-items: center;
  padding: 5px;
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}

.auth-error {
  margin: 3px 2px 0;
  color: var(--danger);
  font-size: 12px;
  line-height: 1.6;
}

.auth-submit {
  min-height: 52px;
  margin-top: 12px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: 13px;
  background: var(--blue);
  color: white;
  cursor: pointer;
  font-size: 14px;
  font-weight: 750;
  box-shadow: 0 13px 28px rgb(37 99 235 / 22%);
}

.auth-submit:disabled {
  cursor: wait;
  opacity: 0.7;
}

.auth-submit svg:last-child {
  margin-left: auto;
}

.auth-footnote {
  margin: 20px 0 0;
  color: #8793a5;
  font-size: 10px;
  line-height: 1.7;
  text-align: center;
}

.auth-spin {
  animation: auth-spin 900ms linear infinite;
}

@keyframes auth-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 900px) {
  .auth-shell {
    grid-template-columns: 1fr;
    align-content: center;
    gap: 36px;
  }

  .auth-story {
    min-height: auto;
    gap: 42px;
  }

  .auth-card {
    max-width: 560px;
    justify-self: start;
  }

  .auth-points {
    display: none;
  }
}

@media (max-width: 620px) {
  .auth-shell {
    padding: 18px 16px 28px;
    align-content: start;
  }

  .auth-story {
    gap: 34px;
  }

  .auth-story h1 {
    font-size: clamp(42px, 13vw, 58px);
  }

  .auth-story p {
    margin-top: 18px;
    font-size: 13px;
  }

  .auth-card {
    padding: 24px 20px;
    border-radius: 20px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-spin {
    animation: none;
  }
}
</style>
