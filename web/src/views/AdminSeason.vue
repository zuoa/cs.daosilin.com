<template>
  <div class="admin-shell">
    <h1>杯赛采集管理</h1>
    <div class="admin-nav">
      <router-link class="on" to="/admin/season">杯赛 / 采集</router-link>
      <router-link to="/admin/players">玩家库</router-link>
      <span class="spacer"></span>
      <router-link to="/">公开首页</router-link>
      <a href="#" @click.prevent="logout">退出</a>
    </div>
    <p class="muted">cup_name 用于 URL（建议英文）；cup_alias 是页面展示名。自定义局需达到库内占比门槛。</p>

    <h2>① 杯赛</h2>
    <div class="card">
      <table class="admin-table">
        <thead>
          <tr>
            <th></th><th>cup_name</th><th>展示名</th><th>类型</th><th>时间段</th><th>门槛</th><th>状态</th><th>种子</th><th>纳入/剔除</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in seasons" :key="s.cup_name" :class="{ current: s.cup_name === currentCup }">
            <td>{{ s.cup_name === currentCup ? '▶' : '' }}</td>
            <td>{{ s.cup_name }}</td>
            <td>{{ s.cup_alias || s.name || '' }}</td>
            <td><span class="tag" :class="s.match_type">{{ s.match_type }}</span></td>
            <td>{{ s.start_date || '' }} ~ {{ s.end_date || '' }}</td>
            <td>{{ pct(s.hit_ratio) }}%</td>
            <td><span class="tag" :class="s.status">{{ s.status }}</span></td>
            <td>{{ s.roster_count }}</td>
            <td>{{ s.approved_count || 0 }} / {{ s.rejected_count || 0 }}</td>
            <td>
              <button class="ghost sm" @click="selectCup(s.cup_name)">选为当前</button>
              <button class="ghost sm" @click="editSeason(s)">编辑</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="card">
      <div class="row">
        <label>cup_name*</label><input v-model="form.cup" placeholder="英文 slug，如 shark-s2">
        <label>cup_alias</label><input v-model="form.alias" placeholder="页面展示名">
        <label>类型</label>
        <select v-model="form.type"><option value="custom">custom</option><option value="official">official</option></select>
        <label>起</label><input v-model="form.start" placeholder="YYYYMMDD">
        <label>止</label><input v-model="form.end" placeholder="YYYYMMDD">
        <label>库内占比%</label><input v-model.number="form.hit" type="number" min="0" max="100" step="5">
        <label>状态</label>
        <select v-model="form.status"><option value="active">active</option><option value="archived">archived</option></select>
        <button class="btn" @click="saveSeason">保存杯赛</button>
      </div>
    </div>

    <h2>② 种子玩家 · {{ currentCup || '' }}</h2>
    <div class="card">
      <div class="muted">{{ rosterText }}</div>
      <div class="row" style="margin-top:12px">
        <label>搜索</label>
        <input v-model="seedQ" placeholder="ID / 昵称 / 别名">
      </div>
      <div class="picker">
        <label v-for="p in filteredLibrary" :key="p.player_id">
          <input type="checkbox" :value="p.player_id" v-model="seedChecked">
          <span>{{ p.alias_name || p.nickname }}</span>
          <span class="muted">({{ p.player_id }})</span>
        </label>
        <div v-if="!filteredLibrary.length" class="muted">玩家库为空，可直接粘贴 ID</div>
      </div>
      <div class="row" style="margin-top:12px;align-items:flex-start">
        <label>player_ids</label>
        <textarea v-model="rosterRaw"></textarea>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="btn" @click="saveRoster">保存种子</button>
      </div>
    </div>

    <h2>③ 采集</h2>
    <div class="card row">
      <button class="btn" :disabled="!currentCup || crawling" @click="startCrawl">立即采集</button>
      <span class="muted">{{ crawlMsg }}</span>
      <span class="spacer"></span>
      <router-link v-if="currentCup" class="ghost-link" :to="`/${currentCup}/`">公开统计页</router-link>
    </div>

    <h2>④ 比赛记录</h2>
    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <button class="btn sm" :class="{ ghost: matchTab !== 'approved' }" @click="switchTab('approved')">已纳入</button>
        <button class="btn sm" :class="{ ghost: matchTab !== 'rejected' }" @click="switchTab('rejected')">已剔除</button>
        <select v-model="dayFilter">
          <option value="">全部比赛日</option>
          <option v-for="d in matchDays" :key="d" :value="d">{{ d }}</option>
        </select>
        <button class="ghost" @click="loadMatches">刷新</button>
        <span class="spacer"></span>
        <button :class="matchTab === 'approved' ? 'danger' : 'btn'" @click="bulk">{{ matchTab === 'approved' ? '剔除选中' : '恢复选中' }}</button>
      </div>
      <table class="admin-table">
        <thead>
          <tr>
            <th><input type="checkbox" @change="toggleAll($event)"></th>
            <th>比赛日</th><th>地图</th><th>对阵</th><th>库内</th><th>玩家</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in visibleMatches" :key="m.match_id">
            <td><input type="checkbox" :value="m.match_id" v-model="checked"></td>
            <td>{{ m.play_day }}</td>
            <td>{{ m.map_name }}<br><span class="muted">{{ m.game_mode }}</span></td>
            <td>{{ m.team1_name }} {{ m.team1_score }} : {{ m.team2_score }} {{ m.team2_name }}</td>
            <td>{{ m.roster_hit_count }}</td>
            <td>
              <span v-for="p in m.players" :key="p.player_id" class="player" :class="{ in: p.in_library }">{{ p.nickname }}</span>
            </td>
            <td>
              <button v-if="matchTab === 'approved'" class="danger sm" @click="act('reject', [m.match_id])">剔除</button>
              <button v-else class="btn sm" @click="act('approve', [m.match_id])">恢复</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!visibleMatches.length" class="muted" style="padding:16px;text-align:center">暂无比赛</div>
    </div>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const seasons = ref([])
const currentCup = ref('')
const library = ref([])
const seedQ = ref('')
const seedChecked = ref([])
const rosterRaw = ref('')
const rosterText = ref('请先选择杯赛')
const form = ref({ cup: '', alias: '', type: 'custom', start: '', end: '', hit: 60, status: 'active' })
const crawlMsg = ref('选择杯赛后可采集')
const crawling = ref(false)
const matchTab = ref('approved')
const matches = ref([])
const dayFilter = ref('')
const checked = ref([])
const toast = ref('')
let timer = null

function pct(r) {
  const n = Number(r)
  if (!n && n !== 0) return 60
  return n <= 1 ? Math.round(n * 100) : Math.round(n)
}
function show(msg) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 2000)
}
const filteredLibrary = computed(() => {
  const q = seedQ.value.toLowerCase()
  return library.value.filter((p) => {
    const blob = `${p.player_id}${p.nickname || ''}${p.alias_name || ''}`.toLowerCase()
    return !q || blob.includes(q)
  })
})
const matchDays = computed(() => [...new Set(matches.value.map((m) => m.play_day).filter(Boolean))].sort().reverse())
const visibleMatches = computed(() => matches.value.filter((m) => !dayFilter.value || m.play_day === dayFilter.value))

watch(seedChecked, (ids) => {
  const extra = rosterRaw.value.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean).filter((id) => !library.value.some((p) => p.player_id === id))
  rosterRaw.value = [...new Set([...extra, ...ids])].join(', ')
})

async function loadSeasons() {
  const data = await api.get('/api/admin/season/list')
  seasons.value = data.seasons || []
  const cur = seasons.value.find((s) => s.cup_name === currentCup.value)
  if (cur) applyCrawl(cur.crawl || {})
}
async function selectCup(cup) {
  currentCup.value = cup
  await Promise.all([loadSeasons(), loadRoster(), loadLibrary(), loadMatches(), refreshCrawl()])
}
function editSeason(s) {
  form.value = {
    cup: s.cup_name,
    alias: s.cup_alias || s.name || '',
    type: s.match_type,
    start: s.start_date || '',
    end: s.end_date || '',
    hit: pct(s.hit_ratio),
    status: s.status,
  }
}
async function saveSeason() {
  if (!form.value.cup.trim()) return show('cup_name 不能为空')
  const data = await api.send('/api/admin/season/save', {
    cup: form.value.cup.trim(),
    cup_alias: form.value.alias,
    match_type: form.value.type,
    start_date: form.value.start,
    end_date: form.value.end,
    status: form.value.status,
    hit_percent: String(form.value.hit || 60),
  })
  show(typeof data === 'string' ? data : '已保存')
  await selectCup(form.value.cup.trim())
}
async function loadLibrary() {
  const data = await api.get('/api/admin/players?in_library=1')
  library.value = data.players || []
}
async function loadRoster() {
  if (!currentCup.value) return
  const data = await api.get('/api/admin/season/roster/get?cup=' + encodeURIComponent(currentCup.value))
  const roster = data.roster || []
  rosterText.value = roster.length
    ? roster.map((r) => `${r.alias_name || r.nickname || r.player_id}`).join(' · ')
    : '种子为空'
  seedChecked.value = roster.map((r) => r.player_id)
  rosterRaw.value = roster.map((r) => r.player_id).join(', ')
}
async function saveRoster() {
  if (!currentCup.value) return show('请先选择杯赛')
  const data = await api.send('/api/admin/season/roster/save', { cup: currentCup.value, player_ids: rosterRaw.value })
  show(typeof data === 'string' ? data : '已保存')
  await loadRoster()
  await loadSeasons()
}
function applyCrawl(st) {
  crawling.value = !!(st.running || st.state === 'running')
  crawlMsg.value = crawling.value ? (st.message || '采集中…') : (st.message || '就绪')
}
async function refreshCrawl() {
  if (!currentCup.value) return
  const st = await api.get('/api/admin/season/crawl/status?cup=' + encodeURIComponent(currentCup.value))
  applyCrawl(st)
  if (crawling.value) {
    if (!timer) timer = setInterval(refreshCrawl, 4000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
    loadMatches()
    loadSeasons()
  }
}
async function startCrawl() {
  const data = await api.get('/api/admin/season/crawl?cup=' + encodeURIComponent(currentCup.value))
  show(typeof data === 'string' ? data : '已开始')
  refreshCrawl()
}
function switchTab(tab) {
  matchTab.value = tab
  checked.value = []
  loadMatches()
}
async function loadMatches() {
  if (!currentCup.value) return
  const data = await api.get(`/api/admin/selection/list?cup=${encodeURIComponent(currentCup.value)}&status=${matchTab.value}`)
  matches.value = data.list || []
}
function toggleAll(e) {
  checked.value = e.target.checked ? visibleMatches.value.map((m) => m.match_id) : []
}
async function act(type, ids) {
  const data = await api.send(`/api/admin/selection/${type}`, { cup: currentCup.value, match_ids: ids.join(',') })
  show(typeof data === 'string' ? data : '完成')
  loadMatches()
  loadSeasons()
}
function bulk() {
  if (!checked.value.length) return show('未勾选')
  act(matchTab.value === 'approved' ? 'reject' : 'approve', checked.value)
}
async function logout() {
  await api.logout()
  router.replace('/admin/login')
}

onMounted(async () => {
  await loadSeasons()
  await loadLibrary()
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
