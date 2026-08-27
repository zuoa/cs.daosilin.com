<template>
  <div class="login-page">
    <aside class="login-visual">
      <router-link class="public-brand inverted" to="/">
        <span class="brand-mark"><AppIcon name="target" :size="23" /></span>
        <span><strong>熊掌CS Major</strong><small>CONTROL ROOM</small></span>
      </router-link>
      <div class="login-visual-copy">
        <h1>管理每一场<br>进入榜单的比赛。</h1>
        <p>杯赛配置、种子名单、数据采集与比赛审核，都从这里开始。</p>
      </div>
      <div class="login-status-list">
        <div><AppIcon name="shield" /><span><strong>会话保护</strong><small>安全 Cookie 与失败锁定</small></span></div>
        <div><AppIcon name="database" /><span><strong>数据可追溯</strong><small>比赛剔除后仍可恢复</small></span></div>
        <div><AppIcon name="activity" /><span><strong>采集状态</strong><small>实时查看后台任务进度</small></span></div>
      </div>
      <div class="login-grid-art" aria-hidden="true"><span></span><span></span><span></span></div>
    </aside>

    <main class="login-form-side">
      <div class="login-form-shell">
        <router-link class="login-back" to="/"><AppIcon name="arrowLeft" />返回公开首页</router-link>
        <div class="login-heading">
          <h2>登录管理后台</h2>
          <p>请输入管理员凭据与验证码。</p>
        </div>

        <div v-if="error" class="inline-alert error" role="alert">
          <AppIcon name="alert" />
          <span><strong>登录未完成</strong>{{ error }}</span>
        </div>

        <form class="login-form stack-form" @submit.prevent="submit">
          <div class="field-group">
            <label for="username">管理员账号</label>
            <input id="username" v-model.trim="username" type="text" required maxlength="64" autocomplete="username" :disabled="locked" autofocus placeholder="输入账号">
          </div>
          <div class="field-group">
            <label for="password">密码</label>
            <input id="password" v-model="password" type="password" required maxlength="128" autocomplete="current-password" :disabled="locked" placeholder="输入密码">
          </div>
          <div class="field-group">
            <div class="label-line"><label for="captcha">图形验证码</label><span>不区分大小写</span></div>
            <div class="captcha-row">
              <input id="captcha" v-model.trim="captcha" type="text" required maxlength="8" autocapitalize="characters" autocomplete="off" :disabled="locked" placeholder="输入验证码">
              <button type="button" class="captcha-button" title="点击刷新验证码" :disabled="locked" @click="refresh">
                <img :src="captchaSrc" width="140" height="48" alt="图形验证码，点击可刷新">
                <span><AppIcon name="refresh" :size="14" />换一张</span>
              </button>
            </div>
          </div>
          <button type="submit" class="button primary login-submit" :disabled="locked || loading">
            <span v-if="loading" class="button-spinner"></span>
            <AppIcon v-else name="shield" />
            {{ submitLabel }}
          </button>
        </form>
        <p class="login-footnote"><AppIcon name="shield" :size="15" />连续失败会触发临时锁定，保护后台数据安全。</p>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const captcha = ref('')
const error = ref('')
const locked = ref(false)
const lockSeconds = ref(0)
const loading = ref(false)
const captchaSrc = ref('/api/admin/captcha?' + Date.now())
let lockTimer

const submitLabel = computed(() => {
  if (loading.value) return '正在验证…'
  if (locked.value) return `请 ${lockSeconds.value || '稍后'} 秒后重试`
  return '安全登录'
})

function refresh() {
  captchaSrc.value = '/api/admin/captcha?' + Date.now()
  captcha.value = ''
}
function startLock(message) {
  const match = String(message).match(/(\d+)\s*秒/)
  lockSeconds.value = Number(match?.[1] || 60)
  locked.value = true
  clearInterval(lockTimer)
  lockTimer = setInterval(() => {
    lockSeconds.value -= 1
    if (lockSeconds.value <= 0) {
      clearInterval(lockTimer)
      locked.value = false
      error.value = ''
      refresh()
    }
  }, 1000)
}
async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.login({ username: username.value, password: password.value, captcha: captcha.value })
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/admin')
      ? route.query.next
      : '/admin/season'
    router.replace(next)
  } catch (e) {
    error.value = e.message
    if ((e.message || '').includes('锁定') || e.status === 429) startLock(e.message)
    refresh()
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => clearInterval(lockTimer))
</script>
