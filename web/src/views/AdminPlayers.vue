<template>
  <AdminLayout
    eyebrow="PLAYER LIBRARY"
    title="玩家库"
    description="维护可信玩家身份，并控制哪些玩家参与自定义比赛的名单命中计算。"
  >
    <template #actions>
      <button class="button primary" type="button" @click="startCreate">
        <AppIcon name="userPlus" />
        新增玩家
      </button>
    </template>

    <section class="metric-grid" aria-label="玩家库概览">
      <article class="metric-card">
        <span class="metric-icon green"><AppIcon name="shield" /></span>
        <div><strong>{{ libraryCount }}</strong><span>库内玩家</span></div>
        <small>参与名单命中</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon blue"><AppIcon name="users" /></span>
        <div><strong>{{ players.length }}</strong><span>当前结果</span></div>
        <small>{{ filterLabel }}</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon amber"><AppIcon name="activity" /></span>
        <div><strong>{{ outsiderCount }}</strong><span>非库内玩家</span></div>
        <small>不参与名单命中</small>
      </article>
    </section>

    <section class="panel data-panel" aria-labelledby="player-list-title">
        <div class="panel-header">
          <div>
            <h2 id="player-list-title">玩家目录</h2>
          </div>
          <span class="result-count">{{ players.length }} 条记录</span>
        </div>

        <div class="data-toolbar">
          <label class="search-field" for="player-search">
            <AppIcon name="search" />
            <input
              id="player-search"
              v-model="q"
              type="search"
              placeholder="搜索 ID、昵称或别名"
              autocomplete="off"
            >
          </label>
          <label class="select-field compact" for="library-filter">
            <AppIcon name="filter" />
            <select id="library-filter" v-model="filterLib">
              <option value="">全部状态</option>
              <option value="1">仅库内</option>
              <option value="0">仅非库内</option>
            </select>
          </label>
          <button class="icon-button" type="button" aria-label="刷新玩家列表" title="刷新" :disabled="loading" @click="load">
            <AppIcon name="refresh" :class="{ spinning: loading }" />
          </button>
        </div>

        <div v-if="checked.length" class="selection-bar" role="status">
          <span><strong>{{ checked.length }}</strong> 名玩家已选中</span>
          <div>
            <button class="button subtle small" type="button" :disabled="busy" @click="bulk(true)">
              <AppIcon name="check" />标为库内
            </button>
            <button class="button danger-ghost small" type="button" :disabled="busy" @click="bulk(false)">
              <AppIcon name="archive" />移出库内
            </button>
          </div>
        </div>

        <div class="table-scroll">
          <table class="data-table admin-player-table">
            <thead>
              <tr>
                <th class="check-cell">
                  <input
                    type="checkbox"
                    :checked="allSelected"
                    aria-label="选择当前页全部玩家"
                    @change="toggleAll"
                  >
                </th>
                <th>玩家</th>
                <th>PLAYER ID</th>
                <th>Steam ID</th>
                <th>直播间</th>
                <th>状态</th>
                <th class="action-cell"><span class="sr-only">操作</span></th>
              </tr>
            </thead>
            <tbody v-if="!loading && players.length">
              <tr v-for="p in players" :key="p.player_id" :class="{ selected: checked.includes(p.player_id) }">
                <td class="check-cell">
                  <input v-model="checked" type="checkbox" :value="p.player_id" :aria-label="`选择 ${displayName(p)}`">
                </td>
                <td>
                  <div class="identity-cell">
                    <PlayerAvatar :src="p.avatar" :name="displayName(p)" class="player-monogram" />
                    <span><strong>{{ displayName(p) }}</strong><small>{{ p.alias_name ? p.nickname : '未设置别名' }}</small></span>
                  </div>
                </td>
                <td><code>{{ p.player_id }}</code></td>
                <td class="muted-cell">{{ p.steam_id || '—' }}</td>
                <td>
                  <a v-if="p.live_url" class="table-link" :href="p.live_url" target="_blank" rel="noopener noreferrer">
                    访问<AppIcon name="external" />
                  </a>
                  <span v-else class="muted-cell">—</span>
                </td>
                <td>
                  <span class="status-badge" :class="p.in_library ? 'success' : 'neutral'">
                    <span class="status-dot"></span>{{ p.in_library ? '库内' : '非库内' }}
                  </span>
                </td>
                <td class="action-cell">
                  <div class="row-actions">
                    <button class="icon-button" type="button" :aria-label="`编辑 ${displayName(p)}`" title="编辑" @click="fill(p)">
                      <AppIcon name="edit" />
                    </button>
                    <button
                      class="button text-button small"
                      type="button"
                      :disabled="busy"
                      @click="setLib([p.player_id], !p.in_library)"
                    >{{ p.in_library ? '移出' : '加入' }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="loading" class="loading-state" aria-live="polite">
          <span class="loader"></span><p>正在加载玩家目录…</p>
        </div>
        <div v-else-if="!players.length" class="empty-state">
          <span><AppIcon name="users" :size="24" /></span>
          <h3>没有找到玩家</h3>
          <p>调整搜索条件，或新增第一名玩家。</p>
          <button class="button subtle" type="button" @click="startCreate">新增玩家</button>
        </div>
    </section>

    <AppModal
      :open="editorOpen"
      :title="isEditing ? '编辑玩家' : '新增玩家'"
      :eyebrow="isEditing ? 'EDIT PROFILE' : 'NEW PROFILE'"
      description="维护公开展示身份与玩家库状态。"
      :persistent="saving"
      @close="closeEditor"
    >
        <form class="stack-form" @submit.prevent="save">
          <div class="field-group">
            <label for="player-id">Player ID <span aria-hidden="true">*</span></label>
            <input id="player-id" ref="idInput" v-model.trim="form.id" required autofocus placeholder="SteamID64 或平台玩家 ID" :disabled="isEditing">
            <small>保存后作为唯一标识，不建议修改。</small>
          </div>
          <div class="field-grid two">
            <div class="field-group">
              <label for="player-nick">原始昵称</label>
              <input id="player-nick" v-model.trim="form.nick" placeholder="比赛数据中的昵称">
            </div>
            <div class="field-group">
              <label for="player-alias">展示别名</label>
              <input id="player-alias" v-model.trim="form.alias" placeholder="公开页优先展示">
            </div>
          </div>
          <div class="field-group">
            <label for="player-steam">Steam ID</label>
            <input id="player-steam" v-model.trim="form.steam" placeholder="可选" @input="steamResolved = false">
          </div>
          <div class="field-group">
            <label for="player-live-room">直播间</label>
            <div class="live-room-input">
              <select v-model="form.livePlatform" aria-label="直播平台">
                <option v-for="platform in livePlatforms" :key="platform.code" :value="platform.code">
                  {{ platform.name }}
                </option>
              </select>
              <input
                id="player-live-room"
                v-model.trim="form.liveRoom"
                placeholder="房间号或完整 URL"
                @input="liveResolved = false"
              >
              <button class="button subtle" type="button" :disabled="resolvingLive || !form.liveRoom" @click="resolveLiveRoom">
                <span v-if="resolvingLive" class="button-spinner"></span>
                {{ resolvingLive ? '获取中…' : '识别直播间' }}
              </button>
            </div>
            <small>可输入房间号，也可直接粘贴完整直播间 URL。</small>
          </div>
          <div class="field-group">
            <label>公开头像</label>
            <div class="avatar-source-picker">
              <label :class="{ active: form.avatarSource === 'wanmei' }">
                <input v-model="form.avatarSource" type="radio" value="wanmei">
                <PlayerAvatar :src="form.wanmeiAvatar" :name="form.alias || form.nick || form.id" />
                <span><strong>完美头像</strong><small>{{ form.wanmeiAvatar ? '来自完美世界比赛资料' : '暂无可用头像' }}</small></span>
              </label>
              <label :class="{ active: form.avatarSource === 'steam' }">
                <input v-model="form.avatarSource" type="radio" value="steam">
                <PlayerAvatar :src="form.steamAvatar" :name="form.alias || form.nick || form.id" />
                <span><strong>Steam 头像</strong><small>{{ steamAvatarLabel }}</small></span>
              </label>
              <label :class="{ active: form.avatarSource === 'live', disabled: form.livePlatform !== 'DOUYU' }">
                <input v-model="form.avatarSource" type="radio" value="live" :disabled="form.livePlatform !== 'DOUYU'">
                <PlayerAvatar :src="form.liveAvatar" :name="form.alias || form.nick || form.id" />
                <span><strong>直播间头像</strong><small>{{ liveAvatarLabel }}</small></span>
              </label>
            </div>
            <div class="avatar-actions">
              <button class="button subtle small" type="button" :disabled="resolvingSteam || !form.steam" @click="resolveSteamAvatar">
                <span v-if="resolvingSteam" class="button-spinner"></span>
                {{ resolvingSteam ? '获取中…' : '获取 Steam 头像' }}
              </button>
            </div>
            <small>斗鱼头像会在保存时重新获取，头像展示统一使用图片代理避免盗链限制。</small>
          </div>
          <label class="switch-row" for="player-library">
            <span>
              <strong>加入玩家库</strong>
              <small>计入自定义比赛的名单命中率</small>
            </span>
            <input id="player-library" v-model="form.lib" type="checkbox" true-value="1" false-value="0">
            <span class="switch-control" aria-hidden="true"></span>
          </label>
          <div class="form-actions">
            <button class="button subtle" type="button" :disabled="saving" @click="closeEditor">取消</button>
            <button class="button primary" type="submit" :disabled="saving">
              <span v-if="saving" class="button-spinner"></span>
              <AppIcon v-else name="save" />
              {{ saving ? '保存中…' : '保存玩家' }}
            </button>
          </div>
        </form>

        <div class="context-note">
          <AppIcon name="shield" />
          <p><strong>名单命中规则</strong><span>只有库内玩家会参与杯赛的库内占比计算，新出现的路人默认保持非库内状态。</span></p>
        </div>
    </AppModal>

    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'">
      <AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />
      {{ toast.message }}
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'

const livePlatforms = [
  { code: 'DOUYU', name: '斗鱼' },
  { code: 'HUYA', name: '虎牙' },
  { code: 'BILIBILI', name: '哔哩哔哩' },
  { code: 'DOUYIN', name: '抖音' },
  { code: 'KUAISHOU', name: '快手' },
  { code: 'CC', name: '网易 CC' },
  { code: 'YY', name: 'YY' },
  { code: 'TWITCH', name: 'Twitch' },
]

const players = ref([])
const q = ref('')
const filterLib = ref('')
const checked = ref([])
const toast = ref({ message: '', type: 'success' })
const loading = ref(false)
const saving = ref(false)
const resolvingLive = ref(false)
const resolvingSteam = ref(false)
const liveResolved = ref(false)
const steamResolved = ref(false)
const busy = ref(false)
const editorOpen = ref(false)
const idInput = ref(null)
const emptyForm = () => ({
  id: '', nick: '', alias: '', steam: '', avatarSource: 'wanmei',
  wanmeiAvatar: '', steamAvatar: '', liveAvatar: '',
  livePlatform: 'DOUYU', liveRoom: '', lib: '1',
})
const form = ref(emptyForm())
let searchTimer
let toastTimer

const isEditing = computed(() => players.value.some((p) => p.player_id === form.value.id))
const libraryCount = computed(() => players.value.filter((p) => p.in_library).length)
const outsiderCount = computed(() => players.value.length - libraryCount.value)
const allSelected = computed(() => players.value.length > 0 && checked.value.length === players.value.length)
const filterLabel = computed(() => ({ '': '全部状态', 1: '仅库内', 0: '仅非库内' }[filterLib.value]))
const steamAvatarLabel = computed(() => {
  if (form.value.steamAvatar) return steamResolved.value ? '已获取 Steam 公开头像' : '已保存的 Steam 头像'
  return form.value.steam ? '可点击下方按钮预览' : '请先填写 Steam ID'
})
const liveAvatarLabel = computed(() => {
  if (form.value.livePlatform !== 'DOUYU') return '该平台头像暂未支持'
  if (form.value.liveAvatar) return liveResolved.value ? '已获取斗鱼主播头像' : '已保存的斗鱼头像'
  return '请先填写并识别斗鱼直播间'
})

function displayName(p) { return p.alias_name || p.nickname || p.player_id }
function show(message, type = 'success') {
  clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => { toast.value.message = '' }, 3000)
}
async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (q.value.trim()) params.set('q', q.value.trim())
    if (filterLib.value !== '') params.set('in_library', filterLib.value)
    const data = await api.get('/api/admin/players?' + params)
    players.value = data.players || []
    checked.value = []
  } catch (e) {
    show(e.message, 'error')
  } finally {
    loading.value = false
  }
}
function fill(p) {
  form.value = {
    id: p.player_id,
    nick: p.nickname || '',
    alias: p.alias_name || '',
    steam: p.steam_id || '',
    avatarSource: p.avatar_source || 'wanmei',
    wanmeiAvatar: p.wanmei_avatar || (p.avatar_source !== 'steam' && p.avatar_source !== 'live' ? p.avatar : '') || '',
    steamAvatar: p.steam_avatar || (p.avatar_source === 'steam' ? p.avatar : '') || '',
    liveAvatar: p.live_avatar || (p.avatar_source === 'live' ? p.avatar : '') || '',
    livePlatform: p.live_platform || 'DOUYU',
    liveRoom: p.live_room || p.live_url || '',
    lib: p.in_library ? '1' : '0',
  }
  liveResolved.value = false
  steamResolved.value = false
  editorOpen.value = true
}
function clearForm() {
  form.value = emptyForm()
  liveResolved.value = false
  steamResolved.value = false
}
function closeEditor() {
  if (saving.value) return
  editorOpen.value = false
  clearForm()
}
async function startCreate() {
  clearForm()
  editorOpen.value = true
  await nextTick()
  idInput.value?.focus()
}
async function save() {
  if (!form.value.id.trim()) return show('请填写 Player ID', 'error')
  saving.value = true
  try {
    const data = await api.send('/api/admin/player/save', {
      player_id: form.value.id.trim(),
      nickname: form.value.nick,
      alias_name: form.value.alias,
      steam_id: form.value.steam,
      avatar_source: form.value.avatarSource,
      live_platform: form.value.livePlatform,
      live_room: form.value.liveRoom,
      in_library: form.value.lib,
    })
    show(typeof data === 'string' ? data : '玩家已保存')
    editorOpen.value = false
    clearForm()
    await load()
  } catch (e) {
    show(e.message, 'error')
  } finally {
    saving.value = false
  }
}
async function resolveLiveRoom() {
  if (!form.value.liveRoom) return show('请填写直播间号或 URL', 'error')
  resolvingLive.value = true
  try {
    const params = new URLSearchParams({
      platform: form.value.livePlatform,
      room: form.value.liveRoom,
      include_avatar: form.value.livePlatform === 'DOUYU' ? '1' : '0',
    })
    const data = await api.get('/api/admin/live-room/resolve?' + params)
    form.value.livePlatform = data.platform
    form.value.liveRoom = data.room_id
    if (data.avatar) form.value.liveAvatar = data.avatar
    liveResolved.value = true
    show(data.avatar ? '已获取直播间头像' : '已识别直播间')
  } catch (e) {
    liveResolved.value = false
    show(e.message, 'error')
  } finally {
    resolvingLive.value = false
  }
}
async function resolveSteamAvatar() {
  if (!form.value.steam) return show('请填写 Steam ID', 'error')
  resolvingSteam.value = true
  try {
    const params = new URLSearchParams({ steam_id: form.value.steam })
    const data = await api.get('/api/admin/steam-avatar/resolve?' + params)
    form.value.steam = data.steam_id
    form.value.steamAvatar = data.avatar
    steamResolved.value = true
    show('已获取 Steam 头像')
  } catch (e) {
    steamResolved.value = false
    show(e.message, 'error')
  } finally {
    resolvingSteam.value = false
  }
}
async function setLib(ids, on) {
  busy.value = true
  try {
    const data = await api.send('/api/admin/player/library', { player_ids: ids.join(','), in_library: on ? '1' : '0' })
    show(typeof data === 'string' ? data : '玩家状态已更新')
    await load()
  } catch (e) {
    show(e.message, 'error')
  } finally {
    busy.value = false
  }
}
function bulk(on) {
  if (!checked.value.length) return show('请先选择玩家', 'error')
  return setLib(checked.value, on)
}
function toggleAll(event) {
  checked.value = event.target.checked ? players.value.map((p) => p.player_id) : []
}

watch([q, filterLib], () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 260)
})
onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  clearTimeout(toastTimer)
})
</script>
