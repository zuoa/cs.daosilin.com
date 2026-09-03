<template>
  <div class="public-site home-page">
    <header class="public-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="23" /></span>
        <span><strong>{{ siteName }}</strong><small>COMPETITIVE DATA</small></span>
      </router-link>
      <nav aria-label="首页导航">
        <a href="#seasons">赛季</a>
        <router-link to="/draft">选人</router-link>
        <router-link :to="adminUser ? '/admin/season' : '/admin/login'" class="button subtle small">
          <AppIcon name="shield" />{{ adminUser ? '管理后台' : '管理登录' }}
        </router-link>
      </nav>
    </header>

    <main>
      <section class="home-hero">
        <div class="hero-copy">
          <h1><span>读懂每一局，</span><span>不止看比分。</span></h1>
        </div>
      </section>

      <section class="home-intro" aria-label="数据档案介绍">
        <div class="home-intro-copy">
          <p class="hero-lead">围绕选手、赛季与比赛日组织的 CS 数据档案。快速找到 Rating、K/D、称号与冠军记录。</p>
          <div class="hero-actions">
            <a class="button primary" href="#seasons">浏览赛季<AppIcon name="arrowRight" /></a>
            <span v-if="lastCrawl" class="update-note"><AppIcon name="activity" />最近更新 {{ formatTime(lastCrawl) }}</span>
          </div>
        </div>

        <div class="hero-telemetry" aria-label="数据概览">
          <div class="telemetry-grid" aria-hidden="true"></div>
          <div class="telemetry-scope" aria-hidden="true">
            <span class="scope-axis horizontal"></span>
            <span class="scope-axis vertical"></span>
            <span class="scope-ring outer"></span>
            <span class="scope-ring inner"></span>
            <span class="scope-pulse"></span>
          </div>
          <div class="telemetry-label top"><span>LIVE INDEX</span><strong>{{ pad(activeCount) }}</strong></div>
          <div class="telemetry-label bottom"><span>ARCHIVED</span><strong>{{ pad(archivedCount) }}</strong></div>
          <div class="telemetry-total"><small>SEASONS</small><strong>{{ pad(seasons.length) }}</strong><span>已收录赛季</span></div>
        </div>
      </section>

      <section id="seasons" class="season-section">
        <div class="section-heading public-heading">
          <h2>选择赛季</h2>
          <p>按杯赛进入总榜，再按比赛日查看当日表现。</p>
        </div>

        <div v-if="loading" class="season-grid">
          <div v-for="i in 3" :key="i" class="season-card skeleton-card" aria-hidden="true">
            <span></span><span></span><span></span>
          </div>
        </div>
        <div v-else-if="error" class="empty-state public-empty" role="alert">
          <span><AppIcon name="alert" :size="26" /></span><h3>数据暂时不可用</h3><p>{{ error }}</p>
          <button class="button subtle" type="button" @click="load">重新加载</button>
        </div>
        <div v-else-if="seasons.length" class="season-grid">
          <router-link
            v-for="(s, index) in seasons"
            :key="s.cup_name"
            class="season-card"
            :class="{ archived: s.status !== 'active' }"
            :to="`/${s.cup_name}/`"
          >
            <div class="season-card-signal">
              <span>{{ pad(index + 1) }}</span>
              <span class="status-badge" :class="s.status === 'active' ? 'success' : 'neutral'">
                <span class="status-dot"></span>{{ s.status === 'active' ? '进行中' : '已归档' }}
              </span>
            </div>
            <div class="season-card-body">
              <span class="season-type">{{ s.match_type === 'official' ? 'OFFICIAL' : 'CUSTOM' }}</span>
              <h3>{{ s.display_name }}</h3>
              <code>/{{ s.cup_name }}</code>
              <div class="season-stats">
                <div><strong>{{ s.match_count || 0 }}</strong><span>比赛</span></div>
                <div><strong>{{ s.day_count || 0 }}</strong><span>比赛日</span></div>
              </div>
            </div>
            <div class="season-card-footer">
              <span><AppIcon name="calendar" />{{ formatRange(s) }}</span>
              <span class="season-enter">查看数据<AppIcon name="arrowRight" /></span>
            </div>
          </router-link>
        </div>
        <div v-else class="empty-state public-empty">
          <span><AppIcon name="layers" :size="26" /></span><h3>还没有公开赛季</h3>
          <p>管理员创建杯赛并完成采集后，数据会出现在这里。</p>
          <router-link class="button subtle" to="/admin/login">进入管理后台</router-link>
        </div>
      </section>
    </main>

    <footer class="public-footer statement-footer"><strong>数据用于比赛复盘与社区统计。</strong><span>{{ siteName }} · CS DATA ARCHIVE · Made with 🩷 By ZUOAJ</span></footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'

const seasons = ref([])
const lastCrawl = ref('')
const siteName = ref('熊掌CS Major')
const adminUser = ref('')
const error = ref('')
const loading = ref(true)
const activeCount = computed(() => seasons.value.filter((s) => s.status === 'active').length)
const archivedCount = computed(() => seasons.value.length - activeCount.value)

function pad(value) { return String(value || 0).padStart(2, '0') }
function formatDateTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '…'
}
function formatRange(season) {
  if (!season.start_date && !season.end_date) return '时间待定'
  return `${formatDateTime(season.start_date)} — ${formatDateTime(season.end_date)}`
}
function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [meta, data] = await Promise.all([api.meta(), api.seasons()])
    adminUser.value = meta.admin_user || ''
    siteName.value = data.site_name || meta.site_name || '熊掌CS Major'
    seasons.value = data.seasons || []
    lastCrawl.value = data.last_crawl_time || ''
    document.title = siteName.value
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
