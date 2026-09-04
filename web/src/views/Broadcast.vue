<template>
  <main
    class="broadcast-overlay"
    :class="[`anchor-${options.anchor}`, { 'is-stale': stale, 'is-paused': paused }]"
    :style="{ '--broadcast-scale': options.scale }"
    :aria-label="`${seasonName}赛事直播数据`"
    tabindex="0"
    data-testid="broadcast-overlay"
    @mouseenter="setTransientPause(true)"
    @mouseleave="setTransientPause(false)"
    @focusin="setTransientPause(true)"
    @focusout="setTransientPause(false)"
  >
    <div class="broadcast-stage">
      <header class="broadcast-header">
        <div class="broadcast-brand">
          <span class="broadcast-brand-mark"><AppIcon name="target" :size="24" /></span>
          <span>
            <strong>{{ seasonName }}</strong>
            <small>熊掌 CS MAJOR · LIVE DATA</small>
          </span>
        </div>
        <div class="broadcast-state" :class="{ warning: stale }">
          <span class="broadcast-state-dot" aria-hidden="true"></span>
          <span>{{ stale ? '数据连接中断' : paused ? '导播锁定' : transientPaused ? '查看暂停' : '数据在线' }}</span>
        </div>
      </header>

      <section v-if="loading && !payload" class="broadcast-placeholder" aria-live="polite">
        <span class="broadcast-loader" aria-hidden="true"></span>
        <strong>正在读取赛季数据</strong>
        <p>叠层将在数据就绪后自动开始轮播。</p>
      </section>

      <section v-else-if="error && !payload" class="broadcast-placeholder broadcast-error" role="alert">
        <AppIcon name="alert" :size="28" />
        <strong>未能载入赛事数据</strong>
        <p>{{ error }} 请按 R 重新读取。</p>
      </section>

      <section v-else-if="payload && !hasBroadcastData" class="broadcast-placeholder broadcast-waiting">
        <AppIcon name="activity" :size="28" />
        <strong>等待首场赛果</strong>
        <p>比赛完成并进入采集后，这里会自动出现比分与选手榜单。</p>
      </section>

      <Transition v-else-if="payload" name="broadcast-panel" mode="out-in">
        <article v-if="activePanel === 0" key="result" class="broadcast-panel result-panel" aria-labelledby="broadcast-result-title">
          <div class="broadcast-panel-meta">
            <div>
              <span>最新赛果</span>
              <strong id="broadcast-result-title">{{ mapName(latestMatch) }}</strong>
            </div>
            <time :datetime="latestMatch?.end_time || ''">{{ formatDay(latestMatch?.play_day) }} · {{ formatClock(latestMatch?.end_time) }}</time>
          </div>

          <div class="broadcast-scoreline">
            <section class="broadcast-team" :class="{ winner: Number(latestMatch?.win_team) === 1 }">
              <div class="broadcast-team-mark" aria-hidden="true">
                <span>{{ teamInitial(latestMatch?.team1_name) }}</span>
                <img
                  v-if="latestMatch?.team1_logo"
                  :src="latestMatch.team1_logo"
                  alt=""
                  width="76"
                  height="76"
                  @error="$event.currentTarget.hidden = true"
                >
              </div>
              <div>
                <span v-if="Number(latestMatch?.win_team) === 1" class="winner-label"><AppIcon name="check" :size="15" />胜方</span>
                <strong>{{ latestMatch?.team1_name || '队伍 A' }}</strong>
              </div>
            </section>

            <div class="broadcast-score" aria-label="最终比分">
              <strong>{{ score(latestMatch?.team1_score) }}</strong>
              <span>:</span>
              <strong>{{ score(latestMatch?.team2_score) }}</strong>
              <small>{{ latestMatch?.game_mode || 'FINAL' }}</small>
            </div>

            <section class="broadcast-team team-two" :class="{ winner: Number(latestMatch?.win_team) === 2 }">
              <div class="broadcast-team-mark" aria-hidden="true">
                <span>{{ teamInitial(latestMatch?.team2_name) }}</span>
                <img
                  v-if="latestMatch?.team2_logo"
                  :src="latestMatch.team2_logo"
                  alt=""
                  width="76"
                  height="76"
                  @error="$event.currentTarget.hidden = true"
                >
              </div>
              <div>
                <span v-if="Number(latestMatch?.win_team) === 2" class="winner-label"><AppIcon name="check" :size="15" />胜方</span>
                <strong>{{ latestMatch?.team2_name || '队伍 B' }}</strong>
              </div>
            </section>
          </div>

          <div v-if="latestMatch?.top_player" class="broadcast-mvp">
            <PlayerAvatar
              :src="latestMatch.top_player.avatar"
              :name="playerName(latestMatch.top_player)"
              class="broadcast-mvp-avatar"
            />
            <div>
              <span>地图最佳表现</span>
              <strong>{{ playerName(latestMatch.top_player) }}</strong>
              <small>{{ latestMatch.top_player.team_name || '本场选手' }}</small>
            </div>
            <dl>
              <div><dt>Rating</dt><dd>{{ n2(latestMatch.top_player.pw_rating || latestMatch.top_player.rating) }}</dd></div>
              <div><dt>K–D</dt><dd>{{ latestMatch.top_player.kill || 0 }}–{{ latestMatch.top_player.death || 0 }}</dd></div>
              <div><dt>ADPR</dt><dd>{{ n1(latestMatch.top_player.adpr) }}</dd></div>
            </dl>
          </div>
        </article>

        <article v-else-if="activePanel === 1" key="leaderboard" class="broadcast-panel leaderboard-panel" aria-labelledby="broadcast-leaderboard-title">
          <div class="broadcast-panel-meta">
            <div>
              <span>赛季排名</span>
              <strong id="broadcast-leaderboard-title">Top 5</strong>
            </div>
            <span>{{ progress.season_completed_maps || 0 }} 张地图计入统计</span>
          </div>
          <ol class="broadcast-ranking">
            <li v-for="player in payload.leaderboard" :key="player.player_id" :class="{ leader: player.rank === 1 }">
              <span class="broadcast-rank">{{ pad(player.rank) }}</span>
              <PlayerAvatar :src="player.avatar" :name="playerName(player)" class="broadcast-rank-avatar" />
              <div class="broadcast-rank-name">
                <strong>{{ playerName(player) }}</strong>
                <small>{{ player.team_name || '暂无队伍' }}</small>
              </div>
              <dl>
                <div><dt>Rating</dt><dd>{{ n2(player.avg_pw_rating) }}</dd></div>
                <div><dt>K/D</dt><dd>{{ n2(player.kd_ratio) }}</dd></div>
                <div><dt>胜率</dt><dd>{{ pct(player.win_rate) }}</dd></div>
              </dl>
            </li>
          </ol>
        </article>

        <article v-else key="progress" class="broadcast-panel progress-panel" aria-labelledby="broadcast-progress-title">
          <div class="broadcast-panel-meta">
            <div>
              <span>赛事进程</span>
              <strong id="broadcast-progress-title">{{ formatDay(progress.current_day) }}</strong>
            </div>
            <span>已完成 {{ progress.completed_days || 0 }} 个比赛日</span>
          </div>

          <dl class="broadcast-progress-stats">
            <div><dt>当前比赛日</dt><dd>{{ progress.today_completed_maps || 0 }}</dd><span>张地图完赛</span></div>
            <div><dt>赛季累计</dt><dd>{{ progress.season_completed_maps || 0 }}</dd><span>张地图入库</span></div>
          </dl>

          <div class="broadcast-recent">
            <div v-for="match in payload.recent_matches" :key="match.match_id" class="broadcast-recent-row">
              <time :datetime="match.end_time || ''">{{ formatClock(match.end_time) }}</time>
              <span class="broadcast-map">{{ mapName(match) }}</span>
              <span :class="{ winner: Number(match.win_team) === 1 }">{{ match.team1_name || '队伍 A' }}</span>
              <strong>{{ score(match.team1_score) }} : {{ score(match.team2_score) }}</strong>
              <span :class="{ winner: Number(match.win_team) === 2 }">{{ match.team2_name || '队伍 B' }}</span>
            </div>
          </div>
        </article>
      </Transition>

      <footer class="broadcast-footer">
        <div class="broadcast-pagination" aria-label="当前播出画面">
          <span v-for="index in 3" :key="index" :class="{ active: activePanel === index - 1 }"></span>
        </div>
        <span>{{ footerStatus }}</span>
        <span v-if="options.debug" class="broadcast-shortcuts">1–3 切屏 · ← → 翻页 · Space 锁定 · R 刷新</span>
      </footer>
    </div>
    <p class="sr-only" aria-live="polite">{{ announcement }}</p>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import {
  BROADCAST_PANEL_DURATIONS,
  broadcastPlayerName,
  formatBroadcastClock,
  formatBroadcastDay,
  isNewBroadcastResult,
  nextBroadcastPanel,
  parseBroadcastOptions,
} from '../broadcast'
import AppIcon from '../components/AppIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'

const route = useRoute()
const options = parseBroadcastOptions(window.location.search)
const payload = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const stale = ref(false)
const error = ref('')
const activePanel = ref(0)
const paused = ref(!options.cycle)
const transientPaused = ref(false)
const announcement = ref('')
let panelTimer = 0
let pollTimer = 0

const seasonName = computed(() => payload.value?.season?.cup_alias || String(route.params.cup || '赛事数据'))
const latestMatch = computed(() => payload.value?.latest_match || null)
const progress = computed(() => payload.value?.progress || {})
const hasBroadcastData = computed(() => Boolean(
  payload.value?.latest_match || payload.value?.leaderboard?.length,
))
const footerStatus = computed(() => {
  if (stale.value) return '保留上次成功数据 · 按 R 重试'
  if (refreshing.value) return '正在检查新赛果'
  const updated = progress.value.last_crawl_time
  return updated ? `数据更新 ${String(updated).replace('T', ' ').slice(5, 16)}` : '等待首次采集'
})

function playerName(player) { return broadcastPlayerName(player) }
function formatDay(value) { return formatBroadcastDay(value) }
function formatClock(value) { return formatBroadcastClock(value) }
function n2(value) { return Number(value || 0).toFixed(2) }
function n1(value) { return Number(value || 0).toFixed(1) }
function pct(value) { return `${(Number(value || 0) * 100).toFixed(0)}%` }
function pad(value) { return String(value || 0).padStart(2, '0') }
function score(value) { return value == null ? '—' : Number(value) }
function teamInitial(value) { return String(value || '?').trim().slice(0, 1).toUpperCase() || '?' }
function mapName(match) { return match?.map_name || match?.map_name_en || '地图待确认' }

function clearPanelTimer() {
  window.clearTimeout(panelTimer)
  panelTimer = 0
}

function schedulePanel(delay = BROADCAST_PANEL_DURATIONS[activePanel.value]) {
  clearPanelTimer()
  if (paused.value || transientPaused.value || !hasBroadcastData.value) return
  panelTimer = window.setTimeout(() => {
    activePanel.value = nextBroadcastPanel(activePanel.value)
    schedulePanel()
  }, delay)
}

function setTransientPause(value) {
  transientPaused.value = Boolean(value)
  schedulePanel()
}

function showPanel(index, announce = true) {
  activePanel.value = nextBroadcastPanel(index, 0)
  if (announce) announcement.value = `已切换到第 ${activePanel.value + 1} 个赛事画面`
  schedulePanel()
}

function stepPanel(direction) {
  activePanel.value = nextBroadcastPanel(activePanel.value, direction)
  announcement.value = `已切换到第 ${activePanel.value + 1} 个赛事画面`
  schedulePanel()
}

function togglePause() {
  paused.value = !paused.value
  announcement.value = paused.value ? '赛事画面已锁定' : '赛事画面继续自动轮播'
  schedulePanel()
}

async function load({ manual = false } = {}) {
  if (refreshing.value) return
  refreshing.value = true
  if (!payload.value) loading.value = true
  error.value = ''
  try {
    const next = await api.broadcast(String(route.params.cup || ''))
    const newResult = isNewBroadcastResult(payload.value, next)
    payload.value = next
    stale.value = false
    document.title = `${seasonName.value} · 赛事直播数据`
    if (newResult) {
      activePanel.value = 0
      announcement.value = '新赛果已更新，正在展示最新比赛'
      schedulePanel(20_000)
    } else if (manual) {
      announcement.value = '赛事数据已刷新'
      schedulePanel()
    } else if (!panelTimer) {
      schedulePanel()
    }
  } catch (cause) {
    error.value = cause.message || '赛事数据读取失败。'
    stale.value = Boolean(payload.value)
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function handleKeydown(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return
  if (['1', '2', '3'].includes(event.key)) {
    event.preventDefault()
    showPanel(Number(event.key) - 1)
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    stepPanel(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    stepPanel(1)
  } else if (event.code === 'Space') {
    event.preventDefault()
    togglePause()
  } else if (event.key.toLowerCase() === 'r') {
    event.preventDefault()
    load({ manual: true })
  }
}

async function resetBroadcast() {
  clearPanelTimer()
  payload.value = null
  activePanel.value = 0
  await load()
}

onMounted(() => {
  document.documentElement.classList.add('broadcast-document')
  window.addEventListener('keydown', handleKeydown)
  load()
  pollTimer = window.setInterval(load, 15_000)
})

onBeforeUnmount(() => {
  clearPanelTimer()
  window.clearInterval(pollTimer)
  window.removeEventListener('keydown', handleKeydown)
  document.documentElement.classList.remove('broadcast-document')
})

watch(() => route.params.cup, resetBroadcast)
</script>
