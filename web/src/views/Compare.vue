<template>
  <div class="public-site compare-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>PLAYER COMPARISON</small></span>
      </router-link>
      <nav aria-label="PLAYER 对比页导航">
        <router-link :to="seasonRoute"><AppIcon name="arrowLeft" />返回榜单</router-link>
      </nav>
    </header>

    <main class="compare-container">
      <section class="compare-intro" aria-labelledby="compare-title">
        <div>
          <p class="compare-context"><span></span>{{ cupAlias || cup }} · {{ day || '赛季总览' }}</p>
          <h1 id="compare-title"><span>PLAYER /</span><span>PLAYER</span></h1>
        </div>
        <div class="compare-intro-copy">
          <p>同一统计范围，逐项看清火力、突破和团队价值。领先只按单项标记，不生成模糊的综合胜者。</p>
          <div class="compare-intro-actions">
            <button class="button subtle" type="button" :aria-expanded="selectorOpen" aria-controls="compare-selector" @click="selectorOpen = !selectorOpen">
              <AppIcon :name="selectorOpen ? 'x' : 'plus'" />{{ selectorOpen ? '收起选手' : '调整选手' }}
            </button>
            <button class="button subtle" type="button" :data-state="copyState" @click="copyLink">
              <AppIcon :name="copyState === 'success' ? 'check' : 'copy'" />{{ copyLabel }}
            </button>
          </div>
        </div>
      </section>

      <div v-if="loading" class="loading-state compare-loading" aria-live="polite"><span class="loader"></span><p>正在装载同一统计范围的选手数据…</p></div>
      <div v-else-if="error" class="empty-state public-empty compare-error" role="alert">
        <span><AppIcon name="alert" :size="26" /></span><h2>无法建立对比</h2><p>{{ error }}</p>
        <button class="button subtle" type="button" @click="load">重新加载</button>
      </div>

      <template v-else>
        <Transition name="selector-reveal">
          <section v-if="selectorOpen || selectedPlayers.length < PLAYER_COMPARE_MINIMUM" id="compare-selector" class="compare-selector" aria-labelledby="selector-title">
            <div class="compare-selector-heading">
              <div><h2 id="selector-title">选择同场 PLAYER</h2><p>最多 4 人；已按 {{ day || '赛季总览' }} 统一统计口径。</p></div>
              <span>{{ selectedPlayers.length }} / {{ PLAYER_COMPARE_LIMIT }}</span>
            </div>
            <label class="compare-search" for="compare-player-search">
              <span>搜索选手或队伍</span>
              <span class="compare-search-field"><AppIcon name="search" /><input id="compare-player-search" v-model="query" type="search" placeholder="例如：选手名、队伍名"></span>
            </label>
            <div v-if="filteredCandidates.length" class="compare-candidate-grid">
              <button
                v-for="player in filteredCandidates"
                :key="player.player_id"
                type="button"
                class="compare-candidate"
                :class="{ selected: isSelected(player.player_id) }"
                :aria-pressed="isSelected(player.player_id)"
                :disabled="!isSelected(player.player_id) && selectedPlayers.length >= PLAYER_COMPARE_LIMIT"
                @click="togglePlayer(player)"
              >
                <PlayerAvatar :src="player.avatar" :name="displayName(player)" />
                <span><strong>{{ displayName(player) }}</strong><small>{{ player.team_name || player.nickname || '暂无队伍' }}</small></span>
                <AppIcon :name="isSelected(player.player_id) ? 'check' : 'plus'" />
              </button>
            </div>
            <p v-else class="compare-selector-empty">没有匹配的选手。换一个名字或队伍试试。</p>
          </section>
        </Transition>

        <section v-if="selectedPlayers.length >= PLAYER_COMPARE_MINIMUM" class="compare-workbench" aria-labelledby="matrix-title">
          <header class="compare-controls">
            <div>
              <h2 id="matrix-title">逐项对照</h2>
              <p>{{ selectedPlayers.length }} 名选手 · 绿色标记当前行领先值</p>
            </div>
            <div class="compare-control-set">
              <div class="compare-segmented" aria-label="指标显示范围">
                <button type="button" :class="{ active: mode === 'featured' }" :aria-pressed="mode === 'featured'" @click="mode = 'featured'">重点</button>
                <button type="button" :class="{ active: mode === 'all' }" :aria-pressed="mode === 'all'" @click="mode = 'all'">全部</button>
              </div>
              <label class="compare-difference-toggle">
                <input v-model="differencesOnly" type="checkbox"><span></span>仅看差异
              </label>
            </div>
          </header>

          <div class="compare-matrix-shell">
            <div class="compare-signal-sweep" aria-hidden="true"></div>
            <div class="compare-matrix-scroll" tabindex="0" aria-label="PLAYER 数据对比表，可横向和纵向滚动">
              <table class="compare-matrix" :class="`players-${selectedPlayers.length}`">
                <caption class="sr-only">{{ cupAlias || cup }} {{ day || '赛季总览' }} PLAYER 数据对比</caption>
                <thead>
                  <tr>
                    <th class="compare-metric-corner" scope="col"><span>指标</span><small>{{ visibleMetricCount }} 项</small></th>
                    <th v-for="(player, index) in selectedPlayers" :key="player.player_id" scope="col" class="compare-player-column">
                      <div class="compare-player-card">
                        <span class="compare-player-index">P{{ index + 1 }}</span>
                        <div class="compare-player-visual">
                          <img v-if="player.portrait?.url" class="compare-player-portrait" :src="player.portrait.url" :alt="`${displayName(player)} 人物图`">
                          <PlayerAvatar v-else :src="player.avatar" :name="displayName(player)" />
                        </div>
                        <div class="compare-player-name"><strong>{{ displayName(player) }}</strong><small>{{ player.team_name || player.nickname || '暂无队伍' }}</small></div>
                        <div v-if="leadLabels(player).length" class="compare-lead-tags" aria-label="单项优势">
                          <span v-for="label in leadLabels(player)" :key="label">{{ label }}</span>
                        </div>
                        <button type="button" :aria-label="`移除 ${displayName(player)}`" @click="removePlayer(player.player_id)"><AppIcon name="x" :size="14" /></button>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody v-for="group in visibleGroups" :key="group.id">
                  <tr class="compare-group-row">
                    <th scope="rowgroup">{{ group.title }}</th>
                    <td :colspan="selectedPlayers.length">{{ group.description }}</td>
                  </tr>
                  <tr v-for="item in group.metrics" :key="item.key" class="compare-metric-row">
                    <th scope="row">
                      <span>{{ item.label }}</span>
                      <small v-if="item.direction !== 'neutral'">{{ item.direction === 'lower' ? '低值优先' : '高值优先' }}</small>
                    </th>
                    <td
                      v-for="player in selectedPlayers"
                      :key="player.player_id"
                      :class="{
                        leader: isLeader(item, player),
                        missing: formatMetric(item, player) === '—' || formatMetric(item, player) === '未覆盖',
                      }"
                    >
                      <strong>{{ formatMetric(item, player) }}</strong>
                      <span v-if="isLeader(item, player)" class="compare-leader-mark"><AppIcon name="arrowUp" :size="12" />领先</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <p class="compare-method-note">总量指标只描述样本，不参与优势判断；Demo 缺失不会按 0 计入比较。</p>
        </section>

        <section v-else class="compare-empty-stage">
          <span><AppIcon name="users" :size="26" /></span>
          <div><h2>至少选择两名 PLAYER</h2><p>从上方加入选手后，这里会按同一统计范围生成纵向对比。</p></div>
        </section>
      </template>
      <p class="sr-only" aria-live="polite">{{ announcement }}</p>
    </main>

    <footer class="public-footer compare-footer"><router-link :to="seasonRoute">返回选手榜单</router-link><span>同口径数据 · 单项领先 · 熊掌CS Major</span></footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import {
  PLAYER_COMPARE_LIMIT,
  PLAYER_COMPARE_MINIMUM,
  addComparedPlayer,
  compareRoute,
  getComparedPlayers,
  hydrateComparedPlayers,
  parseCompareIds,
  removeComparedPlayer,
  replaceComparedPlayers,
} from '../playerCompare'
import {
  formatPlayerMetric,
  leadingPlayerIds,
  metricHasDifference,
  playerLeadMetrics,
  playerMetricGroups,
} from '../playerMetrics'

const route = useRoute()
const router = useRouter()
const cup = computed(() => String(route.params.cup || ''))
const day = computed(() => String(route.params.day || ''))
const cupAlias = ref('')
const candidates = ref([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const selectorOpen = ref(false)
const mode = ref('featured')
const differencesOnly = ref(false)
const announcement = ref('')
const copyState = ref('idle')
let copyResetTimer = 0

const selectedPlayers = computed(() => getComparedPlayers(cup.value, day.value))
const selectedIds = computed(() => selectedPlayers.value.map((player) => String(player.player_id)))
const seasonRoute = computed(() => `/${encodeURIComponent(cup.value)}${day.value ? `/${encodeURIComponent(day.value)}` : ''}/`)
const filteredCandidates = computed(() => {
  const search = query.value.trim().toLowerCase()
  return candidates.value.filter((player) => !search || `${displayName(player)} ${player.nickname || ''} ${player.team_name || ''}`.toLowerCase().includes(search))
})
const visibleGroups = computed(() => playerMetricGroups.map((group) => {
  let metrics = mode.value === 'featured' ? group.metrics.filter((item) => item.featured) : group.metrics
  if (differencesOnly.value) metrics = metrics.filter((item) => metricHasDifference(item, selectedPlayers.value))
  return { ...group, metrics }
}).filter((group) => group.metrics.length))
const visibleMetricCount = computed(() => visibleGroups.value.reduce((sum, group) => sum + group.metrics.length, 0))
const copyLabel = computed(() => ({ success: '链接已复制', error: '复制失败' }[copyState.value] || '复制链接'))

function displayName(player) { return player.alias_name || player.nickname || player.player_id || '选手' }
function isSelected(playerId) { return selectedIds.value.includes(String(playerId)) }
function formatMetric(item, player) { return formatPlayerMetric(item, player) }
function isLeader(item, player) { return leadingPlayerIds(item, selectedPlayers.value).includes(String(player.player_id)) }
function leadLabels(player) { return playerLeadMetrics(player.player_id, selectedPlayers.value).map((item) => item.label) }

function syncUrl() {
  router.replace(compareRoute(cup.value, day.value, selectedIds.value))
}

function togglePlayer(player) {
  if (isSelected(player.player_id)) {
    removeComparedPlayer(cup.value, day.value, player.player_id)
    announcement.value = `已从对比中移除 ${displayName(player)}`
  } else {
    const result = addComparedPlayer(cup.value, day.value, player)
    if (!result.ok) {
      announcement.value = '最多只能同时对比 4 名选手'
      return
    }
    announcement.value = `已将 ${displayName(player)} 加入对比`
  }
  syncUrl()
}

function removePlayer(playerId) {
  const player = selectedPlayers.value.find((item) => String(item.player_id) === String(playerId))
  removeComparedPlayer(cup.value, day.value, playerId)
  announcement.value = `已从对比中移除 ${displayName(player || { player_id: playerId })}`
  selectorOpen.value = selectedPlayers.value.length < PLAYER_COMPARE_MINIMUM
  syncUrl()
}

async function copyLink() {
  window.clearTimeout(copyResetTimer)
  try {
    await navigator.clipboard.writeText(window.location.href)
    copyState.value = 'success'
    announcement.value = '对比链接已复制'
  } catch {
    copyState.value = 'error'
    announcement.value = '浏览器未允许复制，请从地址栏复制链接'
  }
  copyResetTimer = window.setTimeout(() => { copyState.value = 'idle' }, 2200)
}

function reconcileRouteSelection() {
  if (!candidates.value.length) return
  const requestedIds = parseCompareIds(route.query.ids)
  if (!requestedIds.length) {
    hydrateComparedPlayers(cup.value, day.value, candidates.value)
    return
  }
  const byId = new Map(candidates.value.map((player) => [String(player.player_id), player]))
  const valid = requestedIds.map((id) => byId.get(id)).filter(Boolean)
  replaceComparedPlayers(cup.value, day.value, valid)
  if (valid.length !== requestedIds.length) {
    announcement.value = '已忽略当前统计范围内不存在的选手'
    syncUrl()
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.cup(cup.value, day.value || null)
    cupAlias.value = data.cup_alias || data.cup
    candidates.value = data.players || []
    reconcileRouteSelection()
    selectorOpen.value = selectedPlayers.value.length < PLAYER_COMPARE_MINIMUM
    document.title = `PLAYER 对比 · ${cupAlias.value} · 熊掌CS Major`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [route.params.cup, route.params.day], load)
watch(() => route.query.ids, () => {
  if (!loading.value) reconcileRouteSelection()
})
</script>
