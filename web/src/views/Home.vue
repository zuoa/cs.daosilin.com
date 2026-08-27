<template>
  <div class="container home-page">
    <header class="header home-header">
      <div class="header-title">
        <p class="eyebrow">Competitive Stats</p>
        <h1 class="title">{{ siteName }}</h1>
        <p class="subtitle">选择一个赛季查看战绩、称号与冠军</p>
      </div>
      <div class="header-meta home-actions">
        <span v-if="lastCrawl">数据更新 · {{ lastCrawl }}</span>
        <router-link class="ghost-link" :to="adminUser ? '/admin/season' : '/admin/login'">
          {{ adminUser ? '管理后台' : '管理登录' }}
        </router-link>
      </div>
    </header>

    <p v-if="error" class="empty-home">{{ error }}</p>
    <section v-else-if="seasons.length" class="season-grid">
      <router-link
        v-for="s in seasons"
        :key="s.cup_name"
        class="season-card"
        :class="{ 'is-archived': s.status !== 'active' }"
        :to="`/${s.cup_name}/`"
      >
        <div class="season-card-top">
          <span class="tag" :class="s.match_type">{{ s.match_type === 'official' ? '官方' : '自定义' }}</span>
          <span class="tag" :class="s.status">{{ s.status === 'active' ? '进行中' : '已归档' }}</span>
        </div>
        <h2>{{ s.display_name }}</h2>
        <p class="season-slug">/{{ s.cup_name }}/</p>
        <dl class="season-meta">
          <div>
            <dt>时间</dt>
            <dd>{{ s.start_date || s.end_date ? `${s.start_date || '…'} — ${s.end_date || '…'}` : '未设时间段' }}</dd>
          </div>
          <div>
            <dt>场次</dt>
            <dd>{{ s.match_count }} 场 · {{ s.day_count }} 个比赛日</dd>
          </div>
        </dl>
        <span class="season-go">进入数据</span>
      </router-link>
    </section>
    <div v-else class="empty-home">
      <p>还没有赛季。管理员登录后在后台创建杯赛并采集数据。</p>
      <router-link class="ghost-link" to="/admin/login">去登录</router-link>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const seasons = ref([])
const lastCrawl = ref('')
const siteName = ref('CS 数据')
const adminUser = ref('')
const error = ref('')

onMounted(async () => {
  try {
    const [meta, data] = await Promise.all([api.meta(), api.seasons()])
    adminUser.value = meta.admin_user || ''
    siteName.value = data.site_name || meta.site_name || 'CS 数据'
    seasons.value = data.seasons || []
    lastCrawl.value = data.last_crawl_time || ''
    document.title = siteName.value
  } catch (e) {
    error.value = e.message
  }
})
</script>
