<template>
  <div class="admin-app">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="admin-sidebar">
      <router-link class="admin-brand" to="/admin/season" aria-label="熊掌CS Major 管理台首页">
        <span class="brand-mark"><AppIcon name="target" :size="24" /></span>
        <span>
          <strong>熊掌CS Major</strong>
          <small>CONTROL ROOM</small>
        </span>
      </router-link>

      <nav class="admin-menu" aria-label="管理后台导航">
        <p class="admin-menu-label">工作台</p>
        <router-link to="/admin/season">
          <AppIcon name="layers" />
          <span>杯赛与采集</span>
        </router-link>
        <router-link to="/admin/players">
          <AppIcon name="users" />
          <span>玩家库</span>
        </router-link>
        <router-link to="/admin/tasks">
          <AppIcon name="activity" />
          <span>任务中心</span>
        </router-link>
        <router-link to="/admin/settings">
          <AppIcon name="key" />
          <span>API 与安全</span>
        </router-link>
        <p class="admin-menu-label public-label">公开页面</p>
        <router-link class="public-menu-link" to="/">
          <AppIcon name="home" />
          <span>数据首页</span>
          <AppIcon class="menu-external" name="external" :size="14" />
        </router-link>
      </nav>

      <div class="admin-account">
        <span class="account-avatar">{{ initial }}</span>
        <span class="account-copy">
          <strong>{{ username || '管理员' }}</strong>
          <small>已安全登录</small>
        </span>
        <button class="icon-button dark" type="button" aria-label="退出登录" title="退出登录" @click="logout">
          <AppIcon name="logout" />
        </button>
      </div>
    </aside>

    <main id="main-content" class="admin-main" tabindex="-1">
      <header class="admin-topbar">
        <div>
          <h1>{{ title }}</h1>
          <p v-if="description" class="page-description">{{ description }}</p>
        </div>
        <div class="admin-top-actions"><slot name="actions" /></div>
      </header>
      <div class="admin-content"><slot /></div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import AppIcon from './AppIcon.vue'

defineProps({
  eyebrow: { type: String, default: 'ADMIN CONSOLE' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
})

const router = useRouter()
const username = ref('')
const initial = computed(() => (username.value || 'A').slice(0, 1).toUpperCase())

async function logout() {
  try { await api.logout() } finally { router.replace('/admin/login') }
}

onMounted(async () => {
  try {
    const data = await api.me()
    username.value = data.username || ''
  } catch { /* 路由守卫会处理失效会话 */ }
})
</script>
