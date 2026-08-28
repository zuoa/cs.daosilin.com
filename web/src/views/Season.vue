<template>
  <div class="public-site season-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>COMPETITIVE ARCHIVE</small></span>
      </router-link>
      <nav aria-label="赛季页面导航"><router-link to="/"><AppIcon name="layers" />全部赛季</router-link></nav>
    </header>

    <main>
      <section class="season-hero">
        <div class="season-title-block">
          <h1>{{ cupAlias || cup }}</h1>
          <p>{{ day ? `${day} · 当日选手数据` : '赛季综合数据与选手排名' }}</p>
        </div>
        <div class="season-summary" aria-label="赛季数据概览">
          <div><span>选手</span><strong>{{ players.length }}</strong></div>
          <div><span>最高 Rating</span><strong>{{ topRating }}</strong></div>
          <div><span>平均 Rating</span><strong>{{ averageRating }}</strong></div>
          <div><span>数据更新</span><strong class="summary-time">{{ formatTime(lastCrawl) || '—' }}</strong></div>
        </div>
      </section>

      <nav class="day-navigation" aria-label="比赛日筛选">
        <span class="day-nav-label">比赛日</span>
        <div class="day-scroll">
          <router-link :to="`/${cup}/`" class="day-chip" :class="{ active: !day }">
            <span>ALL</span>赛季总览
          </router-link>
          <router-link
            v-for="(d, index) in cupDays"
            :key="d"
            :to="`/${cup}/${d}/`"
            class="day-chip"
            :class="{ active: d === day }"
          ><span>{{ pad(index + 1) }}</span>{{ d }}</router-link>
        </div>
      </nav>

      <section class="leaderboard-section">
        <div class="section-heading public-heading leaderboard-heading">
          <h2>选手榜单</h2>
          <p>{{ day ? '数据按当日表现计算' : '数据按综合 Rating 默认排序' }}</p>
        </div>

        <div class="leaderboard-panel">
          <div class="data-toolbar public-toolbar">
            <label class="search-field" for="season-player-search">
              <AppIcon name="search" /><input id="season-player-search" v-model="query" type="search" placeholder="搜索选手或队伍">
            </label>
            <label class="select-field compact" for="season-sort">
              <AppIcon name="filter" />
              <select id="season-sort" v-model="sortKey">
                <option value="avg_pw_rating">按 Rating</option>
                <option value="kd_ratio">按 K/D</option>
                <option value="win_rate">按胜率</option>
                <option value="avg_adpr">按 ADPR</option>
                <option value="total_mvp">按 MVP</option>
              </select>
            </label>
            <span class="toolbar-summary">{{ filteredPlayers.length }} 名选手</span>
          </div>

          <div v-if="loading" class="loading-state leaderboard-loading" aria-live="polite"><span class="loader"></span><p>正在读取赛季数据…</p></div>
          <div v-else-if="error" class="empty-state public-empty" role="alert">
            <span><AppIcon name="alert" :size="25" /></span><h3>无法读取榜单</h3><p>{{ error }}</p>
            <button class="button subtle" type="button" @click="load">重新加载</button>
          </div>
          <div v-else-if="filteredPlayers.length" class="table-scroll leaderboard-scroll">
            <table class="data-table leaderboard-table">
              <thead>
                <tr>
                  <th class="rank-cell">排名</th><th>选手</th><th>完美段位</th><th v-if="day">称号</th><th>荣誉</th>
                  <th>场次</th><th>胜率</th><th>K/D</th><th>Rating</th><th>ADPR</th><th>WE</th><th>爆头率</th><th>MVP</th><th class="action-cell"><span class="sr-only">查看详情</span></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(p, index) in filteredPlayers" :key="p.player_id">
                  <tr :class="{ expanded: open === p.player_id }">
                    <td class="rank-cell"><span class="rank-number" :class="{ top: index < 3 }">{{ pad(index + 1) }}</span></td>
                    <td>
                      <div class="identity-cell public-player">
                        <PlayerAvatar :src="p.avatar" :name="displayName(p)" class="player-avatar" />
                        <span><strong>{{ displayName(p) }}</strong><small>{{ p.team_name || p.nickname || '—' }}</small></span>
                      </div>
                    </td>
                    <td class="perfect-rank-cell">
                      <PerfectRankBadge
                        v-if="p.perfect_level"
                        :level="p.perfect_level"
                        :score="p.perfect_score"
                        :updated-at="p.perfect_rank_updated_at"
                        compact
                      />
                      <span v-else class="muted-cell">待更新</span>
                    </td>
                    <td v-if="day">
                      <div class="title-container">
                        <span
                          v-for="t in uniqueTitles(p.titles).slice(0, 2)"
                          :key="t.title_name"
                          class="title-badge"
                          :class="`title-${t.title_type}`"
                          :title="t.title_description"
                        >{{ t.title_name }}</span>
                        <span v-if="uniqueTitles(p.titles).length > 2" class="title-more">+{{ uniqueTitles(p.titles).length - 2 }}</span>
                        <span v-if="!uniqueTitles(p.titles).length" class="muted-cell">—</span>
                      </div>
                    </td>
                    <td><div class="trophy-container"><span v-for="(item, ti) in p.trophy_history || []" :key="ti" :class="item.trophy">{{ item.trophy === 'champion' ? '冠' : '亚' }}</span><span v-if="!p.trophy_history?.length">—</span></div></td>
                    <td class="mono-data">{{ p.match_count || 0 }}</td>
                    <td><span :class="{ 'stat-positive': p.win_rate >= 0.6 }">{{ pct(p.win_rate) }}</span></td>
                    <td class="mono-data">{{ n2(p.kd_ratio) }}</td>
                    <td><strong class="rating-value" :class="{ hot: p.avg_pw_rating >= 1.57 }">{{ n2(p.avg_pw_rating) }}</strong></td>
                    <td class="mono-data">{{ n2(p.avg_adpr) }}</td>
                    <td class="mono-data">{{ n2(p.avg_we) }}</td>
                    <td class="mono-data">{{ pct(p.avg_headshot_ratio) }}</td>
                    <td class="mono-data">{{ p.total_mvp || 0 }}</td>
                    <td class="action-cell">
                      <div class="row-actions">
                        <button
                          class="icon-button"
                          type="button"
                          :aria-label="`${open === p.player_id ? '收起' : '展开'} ${displayName(p)} 的快速数据`"
                          :aria-expanded="open === p.player_id"
                          @click="togglePlayer(p.player_id)"
                        ><AppIcon name="chevronDown" :class="{ rotated: open === p.player_id }" /></button>
                        <router-link class="icon-button primary-icon" :to="playerLink(p)" :aria-label="`查看 ${displayName(p)} 的完整详情`" title="完整详情">
                          <AppIcon name="arrowRight" />
                        </router-link>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="open === p.player_id" class="detail-drawer">
                    <td :colspan="day ? 14 : 13">
                      <div class="drawer-content">
                        <div v-if="uniqueTitles(p.titles).length" class="drawer-section titles-drawer">
                          <h3>称号信息</h3>
                          <div class="titles-grid">
                            <div v-for="t in uniqueTitles(p.titles)" :key="t.title_name" class="title-card" :class="`title-${t.title_type}`">
                              <strong>{{ t.title_name }}</strong><p>{{ t.title_description }}</p>
                            </div>
                          </div>
                        </div>
                        <div class="drawer-section">
                          <h3>基础数据</h3>
                          <dl class="quick-stat-grid">
                            <div><dt>胜场</dt><dd>{{ p.win_count || 0 }}</dd></div>
                            <div><dt>首杀 / 首死</dt><dd>{{ p.total_first_kills || 0 }} / {{ p.total_first_deaths || 0 }}</dd></div>
                            <div><dt>2K / 3K / 4K / 5K</dt><dd>{{ p.total_2k || 0 }} / {{ p.total_3k || 0 }} / {{ p.total_4k || 0 }} / {{ p.total_5k || 0 }}</dd></div>
                            <div><dt>1v2 / 1v3 / 1v4 / 1v5</dt><dd>{{ p.total_1v2 || 0 }} / {{ p.total_1v3 || 0 }} / {{ p.total_1v4 || 0 }} / {{ p.total_1v5 || 0 }}</dd></div>
                          </dl>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state public-empty">
            <span><AppIcon name="users" :size="25" /></span><h3>没有匹配的选手</h3><p>调整搜索条件，或切换其他比赛日。</p>
          </div>
        </div>
      </section>
    </main>
    <footer class="public-footer"><router-link to="/">返回全部赛季</router-link><span>{{ cupAlias || cup }} · 熊掌CS Major</span></footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import PerfectRankBadge from '../components/PerfectRankBadge.vue'

const route = useRoute()
const cup = computed(() => route.params.cup)
const day = computed(() => route.params.day || '')
const cupAlias = ref('')
const players = ref([])
const cupDays = ref([])
const lastCrawl = ref('')
const error = ref('')
const loading = ref(true)
const open = ref('')
const query = ref('')
const sortKey = ref('avg_pw_rating')

const filteredPlayers = computed(() => {
  const search = query.value.trim().toLowerCase()
  return players.value
    .filter((p) => !search || `${displayName(p)} ${p.nickname || ''} ${p.team_name || ''}`.toLowerCase().includes(search))
    .slice()
    .sort((a, b) => Number(b[sortKey.value] || 0) - Number(a[sortKey.value] || 0))
})
const topRating = computed(() => players.value.length ? n2(Math.max(...players.value.map((p) => Number(p.avg_pw_rating || 0)))) : '0.00')
const averageRating = computed(() => players.value.length ? n2(players.value.reduce((sum, p) => sum + Number(p.avg_pw_rating || 0), 0) / players.value.length) : '0.00')

function displayName(p) { return p.alias_name || p.nickname || p.player_id }
function n2(value) { return Number(value || 0).toFixed(2) }
function pct(value) { return `${(Number(value || 0) * 100).toFixed(1)}%` }
function pad(value) { return String(value || 0).padStart(2, '0') }
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 16) : '' }
function playerLink(p) { return `/player/${p.player_id}/${cup.value}${day.value ? `/${day.value}` : ''}/` }
function togglePlayer(id) { open.value = open.value === id ? '' : id }
function uniqueTitles(list) {
  const seen = new Set()
  return (list || []).filter((title) => {
    if (seen.has(title.title_name)) return false
    seen.add(title.title_name)
    return true
  })
}
async function load() {
  error.value = ''
  loading.value = true
  open.value = ''
  try {
    const data = await api.cup(cup.value, day.value || null)
    cupAlias.value = data.cup_alias || data.cup
    players.value = data.players || []
    cupDays.value = data.cup_days || []
    lastCrawl.value = data.last_crawl_time || ''
    document.title = `${cupAlias.value}${day.value ? ` · ${day.value}` : ''} · 熊掌CS Major`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [route.params.cup, route.params.day], load)
</script>
