<template>
  <AdminLayout title="任务中心" description="管理 Demo 解析与 AI 球探报告的异步任务。">
    <nav class="segmented-control task-tabs" role="tablist" aria-label="任务类型">
      <button id="demo-tab" type="button" role="tab" :class="{ active: activeTab === 'demo' }" :aria-selected="activeTab === 'demo'" aria-controls="demo-panel" @click="setTab('demo')"><AppIcon name="database" />Demo 分析<span>{{ demoJobCount }}</span></button>
      <button id="scouting-tab" type="button" role="tab" :class="{ active: activeTab === 'scouting' }" :aria-selected="activeTab === 'scouting'" aria-controls="scouting-panel" @click="setTab('scouting')"><AppIcon name="activity" />AI 球探报告<span>{{ summaryJobCount }}</span></button>
    </nav>
    <div v-if="loading" class="loading-state"><span class="loader"></span><p>正在读取任务状态…</p></div>

    <div v-else-if="activeTab === 'demo'" id="demo-panel" class="task-tab-panel" role="tabpanel" aria-labelledby="demo-tab">
      <section class="panel token-panel" aria-labelledby="demo-title">
        <div class="panel-header">
          <div><h2 id="demo-title">Demo Analysis</h2><p>独立 Worker · 新比赛与近 30 天自动回填</p></div>
          <div class="demo-header-actions">
            <span class="status-badge" :class="demo.configured && demo.enabled ? 'success' : 'neutral'"><span class="status-dot"></span>{{ demo.enabled ? (demo.configured ? '运行中' : '待配置') : '功能未启用' }}</span>
            <button class="button small" :class="demo.enabled ? 'danger-ghost' : 'primary'" type="button" :disabled="Boolean(demoBusy) || (!demo.enabled && !demo.configured)" @click="demoAction(demo.enabled ? 'disable' : 'enable')"><span v-if="['enable', 'disable'].includes(demoBusy)" class="button-spinner"></span><AppIcon v-else :name="demo.enabled ? 'archive' : 'play'" />{{ demo.enabled ? '关闭分析' : '开启分析' }}</button>
          </div>
        </div>
        <div class="token-content">
          <div class="token-status-card"><span class="metric-icon" :class="demo.configured ? 'green' : 'slate'"><AppIcon name="database" /></span><div><small>PWA 下载凭证</small><strong>{{ demo.token_hint || '尚未保存 access token' }}</strong><span>{{ demo.steam_id || '需要 SteamID64' }} · {{ demoSourceLabel }}</span></div></div>
          <div v-if="!demo.encryption_ready" class="inline-alert" role="alert"><AppIcon name="shield" /><span><strong>默认采集凭证仍可使用</strong>只有在后台保存覆盖凭证时，才需要配置 DEMO_CREDENTIAL_ENCRYPTION_KEY。</span></div>
          <form class="custom-token-form" @submit.prevent="saveDemoCredential">
            <div class="field-group"><label for="demo-steam-id">PWA SteamID64</label><input id="demo-steam-id" v-model="demoSteamId" autocomplete="off" placeholder="7656119…" :disabled="Boolean(demoBusy)"></div>
            <div class="field-group"><label for="demo-token">PWA access token</label><div class="token-input-line"><input id="demo-token" v-model="demoToken" type="password" autocomplete="new-password" placeholder="仅在保存时传输" :disabled="Boolean(demoBusy)"><button class="button primary" type="submit" :disabled="Boolean(demoBusy) || !demo.encryption_ready || !demoSteamId || demoToken.length < 16"><AppIcon name="save" />加密保存</button></div><small>token 只会在 Worker 内存中解密；日志、接口与任务记录均不返回明文或签名 URL。</small></div>
          </form>
          <div class="token-actions"><div><strong>任务概况</strong><p>{{ demoJobSummary }}</p></div><button class="button subtle" type="button" :disabled="Boolean(demoBusy) || !demo.configured" @click="demoAction('backfill')"><AppIcon name="refresh" />扫描近 30 天</button><button v-if="demo.database_configured" class="button danger-ghost" type="button" :disabled="Boolean(demoBusy)" @click="revokeDemo"><AppIcon name="archive" />删除覆盖凭证</button></div>
        </div>
      </section>

      <section class="panel task-list-panel" aria-labelledby="demo-jobs-title">
        <div class="panel-header"><div><h2 id="demo-jobs-title">最近 Demo 任务</h2></div><span class="result-count">{{ demoJobs.length }} 条</span></div>
        <div v-if="demoJobs.length" class="table-scroll">
          <table class="data-table demo-task-table"><thead><tr><th>比赛</th><th>状态</th><th>尝试</th><th>更新时间</th><th>说明</th><th></th></tr></thead><tbody><tr v-for="job in demoJobs" :key="job.match_id">
            <td><code>{{ job.match_id }}</code></td><td><span class="status-badge" :class="job.status === 'completed' ? 'success' : 'neutral'">{{ job.status }}</span></td><td>{{ job.attempt_count }}</td><td>{{ formatTime(job.updated_at) }}</td><td class="task-error-cell" :title="job.error_message || ''">{{ job.error_message || '未记录错误' }}</td>
            <td><button v-if="isDemoRetryable(job.status)" class="button subtle small" type="button" :disabled="Boolean(demoRetrying) || !demo.enabled" @click="retryDemo(job.match_id)"><span v-if="demoRetrying === job.match_id" class="button-spinner dark"></span><AppIcon v-else name="refresh" />{{ demoRetrying === job.match_id ? '排队中' : '重试' }}</button></td>
          </tr></tbody></table>
        </div>
        <div v-else class="empty-state compact"><span><AppIcon name="database" /></span><h3>暂无 Demo 任务</h3><p>开启分析并扫描最近比赛后，任务会显示在这里。</p></div>
      </section>
    </div>

    <section v-else id="scouting-panel" class="panel ai-summary-admin task-tab-panel" role="tabpanel" aria-labelledby="scouting-tab">
      <div class="panel-header"><div><h2>DeepSeek 赛季球探报告</h2><p>独立 Worker · 数据变化后增量生成</p></div><span class="status-badge" :class="summaryStatus.configured && summaryStatus.redis_configured ? 'success' : 'neutral'"><span class="status-dot"></span>{{ summaryStatus.configured && summaryStatus.redis_configured ? summaryStatus.model : '待配置' }}</span></div>
      <div class="token-content">
        <div v-if="!summaryStatus.configured || !summaryStatus.redis_configured" class="inline-alert" role="alert"><AppIcon name="shield" /><span><strong>部署配置不完整</strong>需要在服务端设置 LLM_API_KEY 和 REDIS_URL；密钥不会保存到数据库。</span></div>
        <div class="summary-admin-toolbar"><label class="field-group"><span>赛季</span><select v-model="summaryCup" @change="loadSummaries"><option value="">全部赛季</option><option v-for="season in seasons" :key="season.cup_name" :value="season.cup_name">{{ season.cup_alias || season.name || season.cup_name }}</option></select></label><div class="summary-counts"><span v-for="(count, key) in summaryStatus.counts" :key="key"><b>{{ key }}</b> {{ count }}</span><span v-if="!Object.keys(summaryStatus.counts || {}).length">暂无任务</span></div><button class="button primary" type="button" :disabled="Boolean(summaryBusy) || !summaryCup || !summaryStatus.configured || !summaryStatus.redis_configured" @click="rebuildSummary()"><span v-if="summaryBusy === 'season'" class="button-spinner"></span><AppIcon v-else name="refresh" />重算该赛季</button></div>
      </div>
      <div v-if="summaryStatus.items?.length" class="table-scroll">
        <table class="data-table summary-admin-table"><thead><tr><th>赛季 / 选手</th><th>标题</th><th>状态</th><th>模型 / Token</th><th>更新时间</th><th>说明</th><th></th></tr></thead><tbody><tr v-for="item in summaryStatus.items" :key="item.id">
          <td><strong>{{ item.cup_name }}</strong><small>{{ item.player_name }} · {{ item.player_id }}</small></td><td>{{ item.headline || '尚未生成' }}</td><td><span class="status-badge" :class="item.status === 'completed' ? 'success' : 'neutral'">{{ item.status }}</span></td><td><small>{{ item.model_name || '未记录模型' }}</small><strong>{{ item.total_tokens ?? '未记录' }}</strong></td><td>{{ formatTime(item.updated_at, true) }}</td><td class="summary-error-cell" :title="item.error_message || ''">{{ item.error_message || '未记录错误' }}</td><td><button class="button subtle small" type="button" :disabled="Boolean(summaryBusy)" @click="rebuildSummary(item.player_id, item.cup_name)">重算</button></td>
        </tr></tbody></table>
      </div>
      <div v-else class="empty-state compact"><span><AppIcon name="activity" /></span><h3>暂无 AI 点评记录</h3><p>选择赛季并点击重算，或等待自动采集后的增量任务。</p></div>
    </section>
    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'"><AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}</div>
  </AdminLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const demo = ref({ configured: false, enabled: false, encryption_ready: false, job_counts: {} })
const demoJobs = ref([])
const demoSteamId = ref('')
const demoToken = ref('')
const demoBusy = ref('')
const demoRetrying = ref('')
const summaryStatus = ref({ configured: false, redis_configured: false, counts: {}, items: [] })
const seasons = ref([])
const summaryCup = ref('')
const summaryBusy = ref('')
const toast = ref({ message: '', type: 'success' })
let toastTimer
const activeTab = computed(() => route.query.tab === 'scouting' ? 'scouting' : 'demo')
const demoJobCount = computed(() => demoJobs.value.length)
const summaryJobCount = computed(() => summaryStatus.value.items?.length || 0)
const demoSourceLabel = computed(() => ({ database: '后台覆盖', wmpvp_default: '默认采集凭证', none: '未配置' }[demo.value.source] || '未配置'))
const demoJobSummary = computed(() => Object.entries(demo.value.job_counts || {}).map(([key, value]) => `${key} ${value}`).join(' · ') || '暂无任务')

function setTab(tab) { router.replace({ query: tab === 'demo' ? {} : { tab } }) }
function formatTime(value, trim = false) { return value ? value.replace('T', ' ').slice(0, trim ? 16 : undefined) : '未记录' }
function isDemoRetryable(status) { return !['completed', 'queued', 'downloading', 'validating', 'parsing'].includes(status) }
function show(message, type = 'success') { clearTimeout(toastTimer); toast.value = { message, type }; toastTimer = setTimeout(() => { toast.value.message = '' }, 3500) }
async function load() {
  loading.value = true
  try {
    const [demoStatus, jobs, summaries, seasonData] = await Promise.all([api.get('/api/admin/demo-settings'), api.get('/api/admin/demo-jobs?limit=30'), api.get('/api/admin/player-summaries?page_size=30'), api.get('/api/admin/season/list')])
    demo.value = demoStatus; demoSteamId.value = demoStatus.steam_id || ''; demoJobs.value = jobs.jobs || []; summaryStatus.value = summaries; seasons.value = seasonData.seasons || []
  } catch (error) { show(error.message, 'error') } finally { loading.value = false }
}
async function demoAction(action, extra = {}) {
  demoBusy.value = action
  try { demo.value = await api.post('/api/admin/demo-settings', { action, ...extra }); demoToken.value = ''; const jobs = await api.get('/api/admin/demo-jobs?limit=30'); demoJobs.value = jobs.jobs || []; show(demo.value.message || 'Demo 配置已更新') }
  catch (error) { show(error.message, 'error') } finally { demoBusy.value = '' }
}
function saveDemoCredential() { demoAction('save', { steam_id: demoSteamId.value.trim(), access_token: demoToken.value.trim() }) }
function revokeDemo() { if (window.confirm('确认删除 PWA Demo 凭证？')) demoAction('revoke') }
async function retryDemo(matchId) {
  demoRetrying.value = matchId
  try {
    const result = await api.post(`/api/admin/demo-jobs/${encodeURIComponent(matchId)}/retry`, {})
    const job = demoJobs.value.find(item => item.match_id === matchId)
    if (job) Object.assign(job, { status: result.status, error_message: result.status === 'queued' ? null : job.error_message, next_retry_at: null })
    show(result.status === 'queued' ? '任务已立即重新排队' : `任务当前状态：${result.status}`)
    const [demoStatus, jobs] = await Promise.all([api.get('/api/admin/demo-settings'), api.get('/api/admin/demo-jobs?limit=30')]); demo.value = demoStatus; demoJobs.value = jobs.jobs || []
  } catch (error) { show(error.message, 'error') } finally { demoRetrying.value = '' }
}
async function loadSummaries() { try { const query = new URLSearchParams({ page_size: '30' }); if (summaryCup.value) query.set('cup', summaryCup.value); summaryStatus.value = await api.get(`/api/admin/player-summaries?${query}`) } catch (error) { show(error.message, 'error') } }
async function rebuildSummary(playerId = '', cupName = '') {
  const cup = cupName || summaryCup.value
  if (!cup) return show('请先选择一个赛季', 'error')
  if (!playerId && !window.confirm('确认重新生成该赛季全部选手的 AI 点评？')) return
  summaryBusy.value = playerId || 'season'
  try { const result = await api.post('/api/admin/player-summaries/rebuild', { cup, player_id: playerId }); show(result.message || 'AI 点评已重新调度'); await loadSummaries() } catch (error) { show(error.message, 'error') } finally { summaryBusy.value = '' }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>
