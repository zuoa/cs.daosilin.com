<template>
  <AdminLayout
    eyebrow="SECURITY"
    title="API 与安全"
    description="管理对外 Player API 与异步 Demo 分析所需的访问凭证。"
  >
    <div v-if="loading" class="loading-state"><span class="loader"></span><p>正在读取 API 配置…</p></div>

    <div v-else class="settings-grid">
      <section class="panel token-panel" aria-labelledby="token-title">
        <div class="panel-header">
          <div>
            <h2 id="token-title">External API Token</h2>
          </div>
          <span class="status-badge" :class="status.configured ? 'success' : 'neutral'">
            <span class="status-dot"></span>{{ status.configured ? '已启用' : '未配置' }}
          </span>
        </div>

        <div class="token-content">
          <div class="token-status-card">
            <span class="metric-icon" :class="status.configured ? 'green' : 'slate'"><AppIcon name="key" /></span>
            <div>
              <small>当前凭证</small>
              <strong>{{ status.hint || '尚未创建 token' }}</strong>
              <span>{{ sourceLabel }}</span>
            </div>
          </div>

          <div v-if="status.environment_locked" class="inline-alert" role="status">
            <AppIcon name="shield" />
            <span>
              <strong>由部署环境管理</strong>
              环境变量 EXTERNAL_API_TOKEN 优先级最高，不能在后台替换。需要变更时请修改部署配置并重启服务。
            </span>
          </div>

          <div v-if="revealedToken" class="revealed-token" role="status" aria-live="polite">
            <div>
              <span>新 token · 仅本次显示</span>
              <code>{{ revealedToken }}</code>
            </div>
            <button class="button primary" type="button" @click="copyToken">
              <AppIcon name="copy" />复制 token
            </button>
          </div>

          <template v-if="!status.environment_locked">
            <div class="token-actions">
              <div>
                <strong>{{ status.configured ? '轮换凭证' : '创建凭证' }}</strong>
                <p>系统生成 256-bit 随机 token，数据库仅保存单向哈希。</p>
              </div>
              <button class="button primary" type="button" :disabled="Boolean(busy)" @click="generateToken">
                <span v-if="busy === 'generate'" class="button-spinner"></span>
                <AppIcon v-else name="refresh" />{{ status.configured ? '生成并替换' : '生成 token' }}
              </button>
            </div>

            <form class="custom-token-form" @submit.prevent="saveCustomToken">
              <div class="field-group">
                <label for="custom-api-token">使用自定义 token</label>
                <div class="token-input-line">
                  <input
                    id="custom-api-token"
                    v-model="customToken"
                    type="password"
                    minlength="32"
                    autocomplete="new-password"
                    placeholder="至少 32 个字符"
                    :disabled="Boolean(busy)"
                  >
                  <button class="button subtle" type="submit" :disabled="Boolean(busy) || customToken.trim().length < 32">
                    <span v-if="busy === 'save'" class="button-spinner dark-spinner"></span>
                    <AppIcon v-else name="save" />保存
                  </button>
                </div>
                <small>自定义值通过 JSON 请求提交，不会出现在 URL 或访问日志中。</small>
              </div>
            </form>
          </template>

          <div v-if="canRevoke" class="danger-zone">
            <div>
              <strong>{{ status.environment_locked ? '删除数据库备用凭证' : '撤销 API 访问' }}</strong>
              <p>{{ status.environment_locked ? '环境变量 token 不受影响。' : '撤销后，所有使用当前 token 的调用会立即失效。' }}</p>
            </div>
            <button class="button danger-ghost" type="button" :disabled="Boolean(busy)" @click="revokeToken">
              <AppIcon name="archive" />撤销
            </button>
          </div>
        </div>
      </section>

      <aside class="panel api-guide-panel" aria-labelledby="api-guide-title">
        <div class="panel-header"><div><h2 id="api-guide-title">调用方式</h2></div></div>
        <div class="api-guide-content">
          <div class="endpoint-block">
            <small>ENDPOINT</small>
            <code>GET {{ status.api_path }}</code>
            <code>GET {{ status.player_api_path }}</code>
          </div>
          <div class="selector-list">
            <div><code>season=all</code><span>全部赛季合并统计</span></div>
            <div><code>season=last</code><span>最近结束的赛季</span></div>
            <div><code>season=&lt;name&gt;</code><span>指定赛季名称</span></div>
            <div><code>steam_id=&lt;id&gt;</code><span>个人接口按 Steam ID 查询</span></div>
            <div><code>room_id=DOUYU_9999</code><span>个人接口按平台 + 房间号查询</span></div>
          </div>
          <div class="request-example">
            <small>AUTHORIZATION HEADER</small>
            <code>Authorization: Bearer YOUR_TOKEN</code>
          </div>
          <div class="context-note api-note">
            <AppIcon name="shield" />
            <p><strong>凭证安全</strong><span>不要把 token 放进查询参数、前端代码或公开文档。建议定期轮换。</span></p>
          </div>
        </div>
      </aside>
    </div>

    <section v-if="!loading" class="panel token-panel" aria-labelledby="demo-title" style="margin-top: 24px">
      <div class="panel-header">
        <div><h2 id="demo-title">Demo Analysis</h2><p>独立 Worker · 新比赛与近 30 天自动回填</p></div>
        <div class="demo-header-actions">
          <span class="status-badge" :class="demo.configured && demo.enabled ? 'success' : 'neutral'">
            <span class="status-dot"></span>{{ demo.enabled ? (demo.configured ? '运行中' : '待配置') : '功能未启用' }}
          </span>
          <button
            class="button small"
            :class="demo.enabled ? 'danger-ghost' : 'primary'"
            type="button"
            :disabled="Boolean(demoBusy) || (!demo.enabled && !demo.configured)"
            @click="demoAction(demo.enabled ? 'disable' : 'enable')"
          >
            <span v-if="['enable', 'disable'].includes(demoBusy)" class="button-spinner"></span>
            <AppIcon v-else :name="demo.enabled ? 'archive' : 'play'" />{{ demo.enabled ? '关闭分析' : '开启分析' }}
          </button>
        </div>
      </div>
      <div class="token-content">
        <div class="token-status-card">
          <span class="metric-icon" :class="demo.configured ? 'green' : 'slate'"><AppIcon name="database" /></span>
          <div><small>PWA 下载凭证</small><strong>{{ demo.token_hint || '尚未保存 access token' }}</strong><span>{{ demo.steam_id || '需要 SteamID64' }} · {{ demo.source === 'database' ? '后台覆盖' : demo.source === 'wmpvp_default' ? '默认采集凭证' : '未配置' }}</span></div>
        </div>
        <div v-if="!demo.encryption_ready" class="inline-alert" role="alert">
          <AppIcon name="shield" /><span><strong>默认采集凭证仍可使用</strong>只有在后台保存覆盖凭证时，才需要配置 DEMO_CREDENTIAL_ENCRYPTION_KEY。</span>
        </div>
        <form class="custom-token-form" @submit.prevent="saveDemoCredential">
          <div class="field-group">
            <label for="demo-steam-id">PWA SteamID64</label>
            <input id="demo-steam-id" v-model="demoSteamId" autocomplete="off" placeholder="7656119…" :disabled="Boolean(demoBusy)">
          </div>
          <div class="field-group">
            <label for="demo-token">PWA access token</label>
            <div class="token-input-line">
              <input id="demo-token" v-model="demoToken" type="password" autocomplete="new-password" placeholder="仅在保存时传输" :disabled="Boolean(demoBusy)">
              <button class="button primary" type="submit" :disabled="Boolean(demoBusy) || !demo.encryption_ready || !demoSteamId || demoToken.length < 16"><AppIcon name="save" />加密保存</button>
            </div>
            <small>token 只会在 Worker 内存中解密；日志、接口与任务记录均不返回明文或签名 URL。</small>
          </div>
        </form>
        <div class="token-actions">
          <div><strong>任务概况</strong><p>{{ demoJobSummary }}</p></div>
          <button class="button subtle" type="button" :disabled="Boolean(demoBusy) || !demo.configured" @click="demoAction('backfill')"><AppIcon name="refresh" />扫描近 30 天</button>
          <button v-if="demo.database_configured" class="button danger-ghost" type="button" :disabled="Boolean(demoBusy)" @click="revokeDemo"><AppIcon name="archive" />删除覆盖凭证</button>
        </div>
      </div>
    </section>

    <section v-if="!loading && demoJobs.length" class="panel" style="margin-top: 24px">
      <div class="panel-header"><div><h2>最近 Demo 任务</h2></div><span class="result-count">{{ demoJobs.length }} 条</span></div>
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>比赛</th><th>状态</th><th>尝试</th><th>更新时间</th><th>说明</th><th></th></tr></thead>
          <tbody><tr v-for="job in demoJobs" :key="job.match_id">
            <td><code>{{ job.match_id }}</code></td><td><span class="status-badge" :class="job.status === 'completed' ? 'success' : 'neutral'">{{ job.status }}</span></td>
            <td>{{ job.attempt_count }}</td><td>{{ job.updated_at?.replace('T', ' ') }}</td><td>{{ job.error_message || '—' }}</td>
            <td><button v-if="!['completed', 'downloading', 'parsing'].includes(job.status)" class="button subtle small" type="button" @click="retryDemo(job.match_id)">重试</button></td>
          </tr></tbody>
        </table>
      </div>
    </section>

    <section v-if="!loading" class="panel ai-summary-admin" aria-labelledby="ai-summary-title" style="margin-top: 24px">
      <div class="panel-header">
        <div><h2 id="ai-summary-title">DeepSeek 赛季球探报告</h2><p>独立 Worker · 数据变化后增量生成</p></div>
        <span class="status-badge" :class="summaryStatus.configured && summaryStatus.redis_configured ? 'success' : 'neutral'">
          <span class="status-dot"></span>{{ summaryStatus.configured && summaryStatus.redis_configured ? summaryStatus.model : '待配置' }}
        </span>
      </div>
      <div class="token-content">
        <div v-if="!summaryStatus.configured || !summaryStatus.redis_configured" class="inline-alert" role="alert">
          <AppIcon name="shield" /><span><strong>部署配置不完整</strong>需要在服务端设置 LLM_API_KEY 和 REDIS_URL；密钥不会保存到数据库。</span>
        </div>
        <div class="summary-admin-toolbar">
          <label class="field-group">
            <span>赛季</span>
            <select v-model="summaryCup" @change="loadSummaries">
              <option value="">全部赛季</option>
              <option v-for="season in seasons" :key="season.cup_name" :value="season.cup_name">{{ season.cup_alias || season.name || season.cup_name }}</option>
            </select>
          </label>
          <div class="summary-counts"><span v-for="(count, key) in summaryStatus.counts" :key="key"><b>{{ key }}</b> {{ count }}</span><span v-if="!Object.keys(summaryStatus.counts || {}).length">暂无任务</span></div>
          <button class="button primary" type="button" :disabled="Boolean(summaryBusy) || !summaryCup || !summaryStatus.configured || !summaryStatus.redis_configured" @click="rebuildSummary()">
            <span v-if="summaryBusy === 'season'" class="button-spinner"></span><AppIcon v-else name="refresh" />重算该赛季
          </button>
        </div>
      </div>
      <div v-if="summaryStatus.items?.length" class="table-scroll">
        <table class="data-table summary-admin-table">
          <thead><tr><th>赛季 / 选手</th><th>标题</th><th>状态</th><th>模型 / Token</th><th>更新时间</th><th>说明</th><th></th></tr></thead>
          <tbody><tr v-for="item in summaryStatus.items" :key="item.id">
            <td><strong>{{ item.cup_name }}</strong><small>{{ item.player_name }} · {{ item.player_id }}</small></td>
            <td>{{ item.headline || '—' }}</td>
            <td><span class="status-badge" :class="item.status === 'completed' ? 'success' : 'neutral'">{{ item.status }}</span></td>
            <td><small>{{ item.model_name || '—' }}</small><strong>{{ item.total_tokens ?? '—' }}</strong></td>
            <td>{{ item.updated_at?.replace('T', ' ').slice(0, 16) || '—' }}</td>
            <td class="summary-error-cell">{{ item.error_message || '—' }}</td>
            <td><button class="button subtle small" type="button" :disabled="Boolean(summaryBusy)" @click="rebuildSummary(item.player_id, item.cup_name)">重算</button></td>
          </tr></tbody>
        </table>
      </div>
      <div v-else class="empty-state compact"><span><AppIcon name="activity" /></span><h3>暂无 AI 点评记录</h3><p>选择赛季并点击重算，或等待自动采集后的增量任务。</p></div>
    </section>

    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'">
      <AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'

const loading = ref(true)
const busy = ref('')
const customToken = ref('')
const revealedToken = ref('')
const status = ref({ configured: false, source: 'none', hint: '', environment_locked: false })
const demo = ref({ configured: false, enabled: false, encryption_ready: false, job_counts: {} })
const demoJobs = ref([])
const demoSteamId = ref('')
const demoToken = ref('')
const demoBusy = ref('')
const summaryStatus = ref({ configured: false, redis_configured: false, counts: {}, items: [] })
const seasons = ref([])
const summaryCup = ref('')
const summaryBusy = ref('')
const toast = ref({ message: '', type: 'success' })
let toastTimer

const sourceLabel = computed(() => ({
  environment: '来源：部署环境变量',
  database: '来源：管理后台（哈希存储）',
  none: '生成后即可调用对外接口',
}[status.value.source] || ''))
const canRevoke = computed(() => status.value.source === 'database' || status.value.database_fallback_configured)
const demoJobSummary = computed(() => Object.entries(demo.value.job_counts || {}).map(([key, value]) => `${key} ${value}`).join(' · ') || '暂无任务')

function show(message, type = 'success') {
  clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => { toast.value.message = '' }, 3500)
}

async function load() {
  loading.value = true
  try {
    const [tokenStatus, demoStatus, jobs, summaries, seasonData] = await Promise.all([
      api.get('/api/admin/external-api-token'), api.get('/api/admin/demo-settings'), api.get('/api/admin/demo-jobs?limit=30'),
      api.get('/api/admin/player-summaries?page_size=30'), api.get('/api/admin/season/list'),
    ])
    status.value = tokenStatus
    demo.value = demoStatus
    demoSteamId.value = demoStatus.steam_id || ''
    demoJobs.value = jobs.jobs || []
    summaryStatus.value = summaries
    seasons.value = seasonData.seasons || []
  } catch (error) {
    show(error.message, 'error')
  } finally {
    loading.value = false
  }
}

async function mutate(action, token = '') {
  busy.value = action
  try {
    const data = await api.post('/api/admin/external-api-token', { action, token })
    status.value = data
    if (data.token) revealedToken.value = data.token
    if (action !== 'generate') revealedToken.value = ''
    customToken.value = ''
    show(data.message || 'API 配置已更新')
  } catch (error) {
    show(error.message, 'error')
  } finally {
    busy.value = ''
  }
}

function generateToken() {
  if (status.value.configured && !window.confirm('生成新 token 后，当前 token 会立即失效。确认继续？')) return
  mutate('generate')
}

function saveCustomToken() {
  const token = customToken.value.trim()
  if (token.length < 32) return show('自定义 token 至少需要 32 个字符', 'error')
  if (status.value.configured && !window.confirm('保存后，当前 token 会立即失效。确认继续？')) return
  mutate('save', token)
}

function revokeToken() {
  if (!window.confirm('确认撤销数据库中保存的 API token？')) return
  mutate('revoke')
}

async function demoAction(action, extra = {}) {
  demoBusy.value = action
  try {
    demo.value = await api.post('/api/admin/demo-settings', { action, ...extra })
    demoToken.value = ''
    const jobs = await api.get('/api/admin/demo-jobs?limit=30')
    demoJobs.value = jobs.jobs || []
    show(demo.value.message || 'Demo 配置已更新')
  } catch (error) { show(error.message, 'error') } finally { demoBusy.value = '' }
}
function saveDemoCredential() { demoAction('save', { steam_id: demoSteamId.value.trim(), access_token: demoToken.value.trim() }) }
function revokeDemo() { if (window.confirm('确认删除 PWA Demo 凭证？')) demoAction('revoke') }
async function retryDemo(matchId) {
  demoBusy.value = 'retry'
  try { await api.post(`/api/admin/demo-jobs/${encodeURIComponent(matchId)}/retry`, {}); show('任务已重新排队'); await load() }
  catch (error) { show(error.message, 'error') } finally { demoBusy.value = '' }
}

async function loadSummaries() {
  try {
    const query = new URLSearchParams({ page_size: '30' })
    if (summaryCup.value) query.set('cup', summaryCup.value)
    summaryStatus.value = await api.get(`/api/admin/player-summaries?${query}`)
  } catch (error) { show(error.message, 'error') }
}

async function rebuildSummary(playerId = '', cupName = '') {
  const cup = cupName || summaryCup.value
  if (!cup) return show('请先选择一个赛季', 'error')
  if (!playerId && !window.confirm('确认重新生成该赛季全部选手的 AI 点评？')) return
  summaryBusy.value = playerId || 'season'
  try {
    const result = await api.post('/api/admin/player-summaries/rebuild', { cup, player_id: playerId })
    show(result.message || 'AI 点评已重新调度')
    await loadSummaries()
  } catch (error) { show(error.message, 'error') } finally { summaryBusy.value = '' }
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(revealedToken.value)
    show('token 已复制到剪贴板')
  } catch {
    show('复制失败，请手动选择 token', 'error')
  }
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>
