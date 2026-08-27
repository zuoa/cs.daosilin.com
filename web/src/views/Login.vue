<template>
  <div class="login-body">
    <main class="login-shell">
      <router-link class="login-back" to="/">← 返回赛季首页</router-link>
      <section class="login-card">
        <p class="eyebrow">Admin</p>
        <h1>后台登录</h1>
        <p class="login-lead">账号、密码与图形验证码。连续失败将暂时锁定。</p>
        <div v-if="error" class="login-error" role="alert">{{ error }}</div>
        <form @submit.prevent="submit">
          <label for="username">账号</label>
          <input id="username" v-model="username" type="text" required maxlength="64" :disabled="locked">
          <label for="password">密码</label>
          <input id="password" v-model="password" type="password" required maxlength="128" :disabled="locked">
          <label for="captcha">验证码</label>
          <div class="captcha-row">
            <input id="captcha" v-model="captcha" type="text" required maxlength="8" autocapitalize="characters" autocomplete="off" :disabled="locked">
            <button type="button" class="captcha-btn" title="点击刷新验证码" @click="refresh">
              <img :src="captchaSrc" width="140" height="48" alt="验证码">
            </button>
          </div>
          <button type="submit" class="login-submit" :disabled="locked || loading">{{ loading ? '登录中…' : '登录' }}</button>
        </form>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const captcha = ref('')
const error = ref('')
const locked = ref(false)
const loading = ref(false)
const captchaSrc = ref('/api/admin/captcha?' + Date.now())

function refresh() {
  captchaSrc.value = '/api/admin/captcha?' + Date.now()
  captcha.value = ''
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
    locked.value = (e.message || '').includes('锁定')
    refresh()
  } finally {
    loading.value = false
  }
}
</script>
