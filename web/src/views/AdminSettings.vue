<template>
  <AdminLayout title="API 与安全" description="管理对外 Player API 的访问凭证与调用方式。">
    <div v-if="loading" class="loading-state"><span class="loader"></span><p>正在读取 API 配置…</p></div>

    <div v-else class="settings-grid">
      <section class="panel token-panel" aria-labelledby="token-title">
        <div class="panel-header">
          <div><h2 id="token-title">External API Token</h2></div>
          <span class="status-badge" :class="status.configured ? 'success' : 'neutral'"><span class="status-dot"></span>{{ status.configured ? '已启用' : '未配置' }}</span>
        </div>
        <div class="token-content">
          <div class="token-status-card">
            <span class="metric-icon" :class="status.configured ? 'green' : 'slate'"><AppIcon name="key" /></span>
            <div><small>当前凭证</small><strong>{{ status.hint || '尚未创建 token' }}</strong><span>{{ sourceLabel }}</span></div>
          </div>
          <div v-if="status.environment_locked" class="inline-alert" role="status"><AppIcon name="shield" /><span><strong>由部署环境管理</strong>环境变量 EXTERNAL_API_TOKEN 优先级最高，不能在后台替换。需要变更时请修改部署配置并重启服务。</span></div>
          <div v-if="revealedToken" class="revealed-token" role="status" aria-live="polite">
            <div><span>新 token · 仅本次显示</span><code>{{ revealedToken }}</code></div>
            <button class="button primary" type="button" @click="copyToken"><AppIcon name="copy" />复制 token</button>
          </div>
          <template v-if="!status.environment_locked">
            <div class="token-actions">
              <div><strong>{{ status.configured ? '轮换凭证' : '创建凭证' }}</strong><p>系统生成 256-bit 随机 token，数据库仅保存单向哈希。</p></div>
              <button class="button primary" type="button" :disabled="Boolean(busy)" @click="generateToken"><span v-if="busy === 'generate'" class="button-spinner"></span><AppIcon v-else name="refresh" />{{ status.configured ? '生成并替换' : '生成 token' }}</button>
            </div>
            <form class="custom-token-form" @submit.prevent="saveCustomToken">
              <div class="field-group">
                <label for="custom-api-token">使用自定义 token</label>
                <div class="token-input-line"><input id="custom-api-token" v-model="customToken" type="password" minlength="32" autocomplete="new-password" placeholder="至少 32 个字符" :disabled="Boolean(busy)"><button class="button subtle" type="submit" :disabled="Boolean(busy) || customToken.trim().length < 32"><span v-if="busy === 'save'" class="button-spinner dark"></span><AppIcon v-else name="save" />保存</button></div>
                <small>自定义值通过 JSON 请求提交，不会出现在 URL 或访问日志中。</small>
              </div>
            </form>
          </template>
          <div v-if="canRevoke" class="danger-zone">
            <div><strong>{{ status.environment_locked ? '删除数据库备用凭证' : '撤销 API 访问' }}</strong><p>{{ status.environment_locked ? '环境变量 token 不受影响。' : '撤销后，所有使用当前 token 的调用会立即失效。' }}</p></div>
            <button class="button danger-ghost" type="button" :disabled="Boolean(busy)" @click="revokeToken"><AppIcon name="archive" />撤销</button>
          </div>
        </div>
      </section>

      <aside class="panel api-guide-panel" aria-labelledby="api-guide-title">
        <div class="panel-header"><div><h2 id="api-guide-title">调用方式</h2></div></div>
        <div class="api-guide-content">
          <div class="endpoint-block"><small>ENDPOINT</small><code>GET {{ status.api_path }}</code><code>GET {{ status.player_api_path }}</code></div>
          <div class="selector-list">
            <div><code>season=all</code><span>全部赛季合并统计</span></div><div><code>season=last</code><span>最近结束的赛季</span></div><div><code>season=&lt;name&gt;</code><span>指定赛季名称</span></div><div><code>steam_id=&lt;id&gt;</code><span>个人接口按 Steam ID 查询</span></div><div><code>room_id=DOUYU_9999</code><span>个人接口按平台 + 房间号查询</span></div>
          </div>
          <div class="request-example"><small>AUTHORIZATION HEADER</small><code>Authorization: Bearer YOUR_TOKEN</code></div>
          <div class="context-note api-note"><AppIcon name="shield" /><p><strong>凭证安全</strong><span>不要把 token 放进查询参数、前端代码或公开文档。建议定期轮换。</span></p></div>
        </div>
      </aside>
    </div>

    <section v-if="!loading" class="panel api-test-panel" aria-labelledby="api-test-title">
      <div class="panel-header">
        <div>
          <h2 id="api-test-title">在线测试</h2>
          <p>从管理后台直接发起真实 External API 请求。</p>
        </div>
        <span v-if="testResult" class="status-badge" :class="testResult.ok ? 'success' : 'error'">
          HTTP {{ testResult.status }}
        </span>
      </div>
      <div class="api-test-layout">
        <form class="api-test-form" @submit.prevent="testExternalApi">
          <div class="field-grid two">
            <div class="field-group">
              <label for="test-endpoint">接口</label>
              <select id="test-endpoint" v-model="testEndpoint">
                <option value="players">选手列表</option>
                <option value="player">单个选手</option>
              </select>
            </div>
            <div class="field-group">
              <label for="test-season">赛季</label>
              <input id="test-season" v-model.trim="testSeason" type="text" placeholder="last、all 或赛季名称">
              <small>留空时按 last 查询。</small>
            </div>
          </div>
          <div v-if="testEndpoint === 'player'" class="field-grid two">
            <div class="field-group">
              <label for="test-identifier-type">查询方式</label>
              <select id="test-identifier-type" v-model="testIdentifierType">
                <option value="steam_id">Steam ID</option>
                <option value="room_id">直播房间 ID</option>
              </select>
            </div>
            <div class="field-group">
              <label for="test-identifier">查询值</label>
              <input id="test-identifier" v-model.trim="testIdentifier" type="text" :placeholder="testIdentifierType === 'steam_id' ? '76561198…' : 'DOUYU_9999'">
            </div>
          </div>
          <div class="field-group">
            <label for="test-api-token">Bearer token</label>
            <input id="test-api-token" v-model="testToken" type="password" autocomplete="off" placeholder="粘贴当前 External API token">
            <small>{{ testTokenHint }}</small>
          </div>
          <div class="api-test-request">
            <code>GET {{ testUrl }}</code>
            <button class="button primary" type="submit" :disabled="testing || !canTest">
              <span v-if="testing" class="button-spinner"></span>
              <AppIcon v-else name="activity" />
              {{ testing ? '请求中' : '发送测试' }}
            </button>
          </div>
        </form>

        <div class="api-test-response" aria-live="polite">
          <div class="api-test-response-head">
            <div><strong>响应结果</strong><small v-if="testResult">{{ testResult.duration }} ms</small></div>
            <button v-if="testResult" class="button text-button small" type="button" @click="copyResponse"><AppIcon name="copy" />复制 JSON</button>
          </div>
          <pre v-if="testResult"><code>{{ formattedTestResult }}</code></pre>
          <div v-else class="api-test-empty">
            <AppIcon name="activity" :size="22" />
            <p>发送请求后，这里会显示 HTTP 状态和完整 JSON。</p>
          </div>
        </div>
      </div>
    </section>
    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'"><AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}</div>
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
const toast = ref({ message: '', type: 'success' })
const testing = ref(false)
const testEndpoint = ref('players')
const testSeason = ref('last')
const testIdentifierType = ref('steam_id')
const testIdentifier = ref('')
const testToken = ref('')
const testResult = ref(null)
let toastTimer
const sourceLabel = computed(() => ({ environment: '来源：部署环境变量', database: '来源：管理后台（哈希存储）', none: '生成后即可调用对外接口' }[status.value.source] || ''))
const canRevoke = computed(() => status.value.source === 'database' || status.value.database_fallback_configured)
const testUrl = computed(() => {
  const isPlayer = testEndpoint.value === 'player'
  const path = isPlayer
    ? (status.value.player_api_path || '/api/v1/external/player')
    : (status.value.api_path || '/api/v1/external/players')
  const query = new URLSearchParams({ season: testSeason.value || 'last' })
  if (isPlayer && testIdentifier.value) query.set(testIdentifierType.value, testIdentifier.value)
  return `${path}?${query}`
})
const canTest = computed(() => Boolean(
  testToken.value.trim()
  && (testEndpoint.value === 'players' || testIdentifier.value.trim()),
))
const testTokenHint = computed(() => revealedToken.value
  ? '已自动填入本次新生成的 token。'
  : '已保存的 token 无法读取明文，请输入原始值；token 只保留在当前页面。')
const formattedTestResult = computed(() => JSON.stringify(testResult.value?.body ?? {}, null, 2))

function show(message, type = 'success') { clearTimeout(toastTimer); toast.value = { message, type }; toastTimer = setTimeout(() => { toast.value.message = '' }, 3500) }
async function load() { loading.value = true; try { status.value = await api.get('/api/admin/external-api-token') } catch (error) { show(error.message, 'error') } finally { loading.value = false } }
async function mutate(action, token = '') {
  busy.value = action
  try {
    const data = await api.post('/api/admin/external-api-token', { action, token })
    status.value = data
    if (data.token) {
      revealedToken.value = data.token
      testToken.value = data.token
    }
    if (action === 'save') testToken.value = token
    if (action !== 'generate') revealedToken.value = ''
    customToken.value = ''
    show(data.message || 'API 配置已更新')
  }
  catch (error) { show(error.message, 'error') }
  finally { busy.value = '' }
}
function generateToken() { if (status.value.configured && !window.confirm('生成新 token 后，当前 token 会立即失效。确认继续？')) return; mutate('generate') }
function saveCustomToken() { const token = customToken.value.trim(); if (token.length < 32) return show('自定义 token 至少需要 32 个字符', 'error'); if (status.value.configured && !window.confirm('保存后，当前 token 会立即失效。确认继续？')) return; mutate('save', token) }
function revokeToken() { if (window.confirm('确认撤销数据库中保存的 API token？')) mutate('revoke') }
async function copyToken() { try { await navigator.clipboard.writeText(revealedToken.value); show('token 已复制到剪贴板') } catch { show('复制失败，请手动选择 token', 'error') } }
async function testExternalApi() {
  if (!canTest.value) return
  testing.value = true
  testResult.value = null
  const startedAt = performance.now()
  try {
    const response = await fetch(testUrl.value, {
      credentials: 'same-origin',
      headers: { Authorization: `Bearer ${testToken.value.trim()}` },
    })
    const raw = await response.text()
    let body
    try { body = raw ? JSON.parse(raw) : null } catch { body = { raw } }
    testResult.value = {
      ok: response.ok,
      status: response.status,
      duration: Math.round(performance.now() - startedAt),
      body,
    }
  } catch (error) {
    testResult.value = {
      ok: false,
      status: 'NETWORK_ERROR',
      duration: Math.round(performance.now() - startedAt),
      body: { success: false, message: error.message || '网络请求失败' },
    }
  } finally {
    testing.value = false
  }
}
async function copyResponse() {
  try { await navigator.clipboard.writeText(formattedTestResult.value); show('响应 JSON 已复制') }
  catch { show('复制失败，请手动选择响应内容', 'error') }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>
