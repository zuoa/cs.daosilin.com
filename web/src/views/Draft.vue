<template>
  <div class="public-site draft-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>{{ siteName }}</strong><small>COMPETITIVE ARCHIVE</small></span>
      </router-link>
      <nav aria-label="选人页面导航">
        <router-link to="/"><AppIcon name="home" />数据首页</router-link>
      </nav>
    </header>

    <main class="draft-main">
      <section class="draft-hero">
        <div class="draft-title">
          <p class="draft-kicker">DRAFT BOARD</p>
          <h1>选人结果</h1>
          <p>{{ selected ? `${formatDay(selected.play_day)} 完成的队伍与选人顺位` : '等待新一轮选人完成' }}</p>
        </div>
        <dl v-if="selected" class="draft-summary" aria-label="选人数据概览">
          <div><dt>队伍</dt><dd>{{ selected.team_count }}</dd></div>
          <div><dt>入队选手</dt><dd>{{ selected.player_count }}</dd></div>
          <div><dt>对阵</dt><dd>{{ selected.groups.length }}</dd></div>
          <div><dt>完成时间</dt><dd class="summary-time">{{ formatTime(selected.completed_at) }}</dd></div>
        </dl>
      </section>

      <section v-if="data.days.length" class="draft-filters" aria-label="终稿切换">
        <div class="draft-filter-row">
          <span>比赛日</span>
          <div class="draft-filter-scroll">
            <button
              v-for="day in data.days"
              :key="day"
              type="button"
              :class="{ active: selectedDay === day }"
              @click="chooseDay(day)"
            >{{ formatDay(day) }}</button>
          </div>
        </div>
        <div v-if="data.sessions.length > 1" class="draft-filter-row">
          <span>当日轮次</span>
          <div class="draft-filter-scroll">
            <button
              v-for="session in chronologicalSessions"
              :key="session.id"
              type="button"
              :class="{ active: selected?.id === session.id }"
              @click="chooseSession(session)"
            >{{ formatClock(session.completed_at) }}</button>
          </div>
        </div>
      </section>

      <section v-if="loading" class="draft-grid" aria-live="polite" aria-label="正在读取选人结果">
        <article v-for="index in 4" :key="index" class="matchup-card draft-skeleton" aria-hidden="true">
          <span class="skeleton-line short"></span>
          <div><span></span><span></span></div>
          <div class="skeleton-rosters"><span></span><span></span></div>
        </article>
      </section>

      <section v-else-if="error" class="draft-feedback" role="alert">
        <span><AppIcon name="alert" :size="26" /></span>
        <h2>无法读取选人结果</h2>
        <p>{{ error }}</p>
        <button class="button subtle" type="button" @click="load(false)">重新加载</button>
      </section>

      <section v-else-if="!selected" class="draft-feedback">
        <span><AppIcon name="users" :size="27" /></span>
        <h2>还没有选人终稿</h2>
        <p>监听到新一轮完整分组后，队伍和选人顺位会显示在这里。</p>
      </section>

      <section v-else class="draft-grid" aria-label="分组对阵">
        <article v-for="group in selected.groups" :key="group.name" class="matchup-card">
          <header class="matchup-heading">
            <div><span>对阵分组</span><h2>{{ group.name }}</h2></div>
            <span>{{ totalPlayers(group) }} 名选手</span>
          </header>
          <div class="matchup-body">
            <template v-for="(team, teamIndex) in group.teams" :key="team.team_num">
              <section class="draft-team" :aria-label="`${team.captain_nickname} 队`">
                <header>
                  <div>
                    <span>TEAM {{ team.team_num + 1 }}</span>
                    <h3>{{ team.captain_nickname }}队</h3>
                  </div>
                  <div class="team-roll"><span>ROLL</span><strong>{{ team.roll }}</strong></div>
                </header>
                <ol>
                  <li v-for="player in team.players" :key="`${team.team_num}-${player.slot}`">
                    <span class="slot-label" :class="{ captain: player.is_captain }">
                      {{ player.is_captain ? '队长' : `第 ${player.slot - 1} 选` }}
                    </span>
                    <strong>{{ player.nickname }}</strong>
                    <span v-if="player.needs_steam" class="identity-pending">身份待补</span>
                  </li>
                </ol>
              </section>
              <div v-if="teamIndex === 0" class="versus" aria-hidden="true"><span>VS</span></div>
            </template>
          </div>
        </article>
      </section>
    </main>

    <footer class="public-footer">
      <router-link to="/">返回数据首页</router-link>
      <span>{{ siteName }} · DRAFT ARCHIVE</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import {
  chronologicalDraftSessions,
  draftGroupPlayerCount,
  draftRoute,
  formatDraftClock,
  formatDraftDay,
} from '../draft'

const route = useRoute()
const router = useRouter()
const data = reactive({ days: [], sessions: [], selected_session: null })
const siteName = ref('熊掌CS Major')
const loading = ref(true)
const error = ref('')
let refreshTimer = 0
let requestSequence = 0

const selected = computed(() => data.selected_session)
const selectedDay = computed(() => selected.value?.play_day || String(route.query.day || ''))
const chronologicalSessions = computed(() => chronologicalDraftSessions(data.sessions))

const formatDay = formatDraftDay
const formatClock = (value) => formatDraftClock(value)
const formatTime = (value) => formatDraftClock(value, true)
const totalPlayers = draftGroupPlayerCount

async function load(silent = false) {
  const sequence = ++requestSequence
  if (!silent) loading.value = true
  if (!silent) error.value = ''
  try {
    const result = await api.draft(route.query.day, route.query.session_id)
    if (sequence !== requestSequence) return
    siteName.value = result.site_name || '熊掌CS Major'
    data.days = result.days || []
    data.sessions = result.sessions || []
    data.selected_session = result.selected_session || null
    error.value = ''
  } catch (e) {
    if (sequence !== requestSequence) return
    if (!silent || !selected.value) error.value = e.message
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function chooseDay(day) {
  router.replace(draftRoute(day))
}
function chooseSession(session) {
  router.replace(draftRoute(session.play_day, session.id))
}
function refreshWhenVisible() {
  if (!document.hidden) load(true)
}

watch(() => [route.query.day, route.query.session_id], () => load(false))
onMounted(() => {
  load(false)
  refreshTimer = window.setInterval(refreshWhenVisible, 15000)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  window.clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<style scoped>
.draft-page { min-height: 100dvh; }
.draft-main { width: min(1420px, calc(100% - 64px)); min-height: calc(100dvh - 154px); margin: 0 auto; padding: 34px 0 72px; }
.draft-hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(520px, .92fr); align-items: end; gap: 48px; padding: 42px 0 38px; }
.draft-kicker { color: var(--signal-dark); font-family: var(--font-outlier); font-size: .68rem; font-weight: 800; letter-spacing: .13em; }
.draft-title h1 { margin-top: 9px; font-family: var(--font-display); font-size: clamp(3rem, 6vw, 5.6rem); letter-spacing: -.065em; line-height: .9; }
.draft-title > p:last-child { margin-top: 16px; color: var(--ink-500); font-size: .9rem; }
.draft-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--line-strong); border-bottom: 1px solid var(--line-strong); }
.draft-summary div { min-width: 0; padding: 17px 15px; border-left: 1px solid var(--line); }
.draft-summary div:first-child { border-left: 0; }
.draft-summary dt { color: var(--ink-500); font-size: .65rem; font-weight: 700; }
.draft-summary dd { margin-top: 5px; font-family: var(--font-display); font-size: 1.55rem; font-weight: 800; line-height: 1; }
.draft-summary dd.summary-time { font-family: var(--font-outlier); font-size: .85rem; line-height: 1.45; }
.draft-filters { margin-bottom: 30px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: var(--surface); }
.draft-filter-row { display: grid; grid-template-columns: 96px minmax(0, 1fr); align-items: center; min-height: 57px; }
.draft-filter-row + .draft-filter-row { border-top: 1px solid var(--line); }
.draft-filter-row > span { padding-left: 18px; color: var(--ink-500); font-size: .68rem; font-weight: 750; }
.draft-filter-scroll { display: flex; gap: 7px; min-width: 0; overflow-x: auto; padding: 9px 14px; scrollbar-width: thin; }
.draft-filter-scroll button { min-height: 35px; flex: 0 0 auto; border: 1px solid transparent; border-radius: var(--radius-input); padding: 7px 12px; background: transparent; color: var(--ink-600); font-size: .75rem; font-weight: 700; transition: background-color var(--dur-short) var(--ease-out), border-color var(--dur-short) var(--ease-out), color var(--dur-short) var(--ease-out), transform var(--dur-micro) var(--ease-out); }
.draft-filter-scroll button:hover { border-color: var(--line); background: var(--surface-soft); color: var(--ink-900); }
.draft-filter-scroll button:active { transform: translateY(1px); }
.draft-filter-scroll button.active { border-color: var(--ink-900); background: var(--ink-900); color: var(--color-accent-ink); }
.draft-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.matchup-card { min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-card); }
.matchup-heading { display: flex; min-height: 67px; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.matchup-heading > div { display: flex; align-items: baseline; gap: 10px; }
.matchup-heading span { color: var(--ink-500); font-size: .64rem; font-weight: 700; }
.matchup-heading h2 { font-family: var(--font-display); font-size: 1.45rem; letter-spacing: -.035em; }
.matchup-body { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.draft-team { min-width: 0; padding: 18px; }
.draft-team + .draft-team { border-left: 1px solid var(--line); }
.draft-team > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; min-height: 48px; }
.draft-team > header > div:first-child { min-width: 0; }
.draft-team > header span { color: var(--ink-500); font-family: var(--font-outlier); font-size: .58rem; font-weight: 700; letter-spacing: .06em; }
.draft-team h3 { overflow: hidden; margin-top: 3px; font-family: var(--font-display); font-size: 1.12rem; letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
.team-roll { flex: 0 0 auto; text-align: right; }
.team-roll strong { display: block; margin-top: 1px; color: var(--signal-dark); font-family: var(--font-outlier); font-size: 1.18rem; line-height: 1; }
.draft-team ol { display: grid; gap: 5px; margin: 14px 0 0; padding: 0; list-style: none; }
.draft-team li { display: grid; grid-template-columns: 54px minmax(0, 1fr) auto; min-height: 36px; align-items: center; gap: 9px; border-radius: var(--radius-input); padding: 5px 8px; background: var(--surface-soft); }
.draft-team li strong { overflow: hidden; font-size: .78rem; text-overflow: ellipsis; white-space: nowrap; }
.slot-label { color: var(--ink-500); font-family: var(--font-outlier); font-size: .58rem; }
.slot-label.captain { color: var(--signal-dark); font-family: var(--font-body); font-weight: 800; }
.identity-pending { color: var(--amber); font-size: .57rem; font-weight: 750; white-space: nowrap; }
.versus { position: absolute; z-index: var(--z-raised); top: 16px; left: 50%; display: grid; width: 30px; height: 30px; place-items: center; border: 1px solid var(--line-strong); border-radius: 50%; background: var(--canvas); color: var(--ink-500); font-family: var(--font-outlier); font-size: .57rem; font-weight: 800; transform: translateX(-50%); }
.draft-feedback { display: flex; min-height: 390px; align-items: center; justify-content: center; flex-direction: column; border: 1px solid var(--line); border-radius: var(--radius-panel); background: var(--surface); text-align: center; }
.draft-feedback > span { display: grid; width: 56px; height: 56px; place-items: center; border-radius: var(--radius-card); background: var(--signal-soft); color: var(--signal-dark); }
.draft-feedback h2 { margin-top: 15px; font-family: var(--font-display); font-size: 1.25rem; }
.draft-feedback p { max-width: 30rem; margin-top: 6px; color: var(--ink-500); font-size: .8rem; }
.draft-feedback .button { margin-top: 17px; }
.draft-skeleton { min-height: 330px; padding: 20px; }
.draft-skeleton > span, .draft-skeleton > div > span { display: block; border-radius: 6px; background: var(--gradient-skeleton); background-size: 200% 100%; animation: draftShimmer 1.4s linear infinite; }
.draft-skeleton > .short { width: 28%; height: 18px; }
.draft-skeleton > div:nth-child(2) { display: grid; grid-template-columns: 1fr 1fr; gap: 38px; margin-top: 34px; }
.draft-skeleton > div:nth-child(2) span { height: 26px; }
.skeleton-rosters { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 22px; }
.skeleton-rosters span { height: 190px; }
@keyframes draftShimmer { to { background-position: -200% 0; } }

@media (max-width: 61.25rem) {
  .draft-main { width: min(100% - 36px, 900px); }
  .draft-hero { grid-template-columns: 1fr; gap: 28px; }
  .draft-grid { grid-template-columns: 1fr; }
}
@media (max-width: 45rem) {
  .draft-main { width: calc(100% - 28px); padding-top: 18px; }
  .draft-hero { padding: 25px 0 28px; }
  .draft-title h1 { font-size: clamp(2.8rem, 16vw, 4.2rem); }
  .draft-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .draft-summary div:nth-child(3) { border-top: 1px solid var(--line); border-left: 0; }
  .draft-summary div:nth-child(4) { border-top: 1px solid var(--line); }
  .draft-filter-row { grid-template-columns: 1fr; }
  .draft-filter-row > span { padding: 10px 14px 0; }
  .draft-filter-scroll { padding-top: 7px; }
  .matchup-body { grid-template-columns: 1fr; }
  .draft-team + .draft-team { border-top: 1px solid var(--line); border-left: 0; }
  .versus { position: relative; top: auto; left: auto; width: auto; height: 1px; margin: 0 15px; border: 0; border-radius: 0; background: var(--line); transform: none; }
  .versus span { position: absolute; top: 50%; left: 0; display: grid; width: 28px; height: 28px; place-items: center; border: 1px solid var(--line-strong); border-radius: 50%; background: var(--canvas); transform: translateY(-50%); }
  .draft-team { padding: 17px 15px; }
  .draft-team li { grid-template-columns: 54px minmax(0, 1fr); }
  .identity-pending { grid-column: 2; margin-top: -4px; }
}
@media (prefers-reduced-motion: reduce) {
  .draft-skeleton > span, .draft-skeleton > div > span { animation: none; }
  .draft-filter-scroll button { transition: none; }
}
</style>
