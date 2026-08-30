<template>
  <div class="public-site player-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>PLAYER INTELLIGENCE</small></span>
      </router-link>
      <nav aria-label="选手详情导航">
        <router-link v-if="cup" :to="`/${cup}/${day || ''}`"><AppIcon name="arrowLeft" />返回榜单</router-link>
      </nav>
    </header>

    <main class="player-detail-container">
      <div v-if="loading" class="loading-state player-loading" aria-live="polite"><span class="loader"></span><p>正在建立选手数据档案…</p></div>
      <div v-else-if="error" class="empty-state public-empty player-error" role="alert">
        <span><AppIcon name="alert" :size="26" /></span><h2>无法读取选手档案</h2><p>{{ error }}</p>
        <router-link class="button subtle" :to="cup ? `/${cup}/` : '/'">返回榜单</router-link>
      </div>

      <template v-else-if="player && stats">
        <section class="player-profile-hero">
          <div class="player-profile-main">
            <PlayerAvatar :src="player.avatar" :name="playerName" class="profile-avatar" />
            <div class="profile-copy">
              <div class="profile-name-line">
                <h1>{{ playerName }}</h1>
                <div class="profile-meta-actions">
                  <PerfectRankBadge
                    v-if="player.perfect_level"
                    :level="player.perfect_level"
                    :score="player.perfect_score"
                    :updated-at="player.perfect_rank_updated_at"
                    large
                  />
                  <span v-if="day" class="status-badge neutral">{{ day }}</span>
                  <span v-if="stats.demo_coverage" class="status-badge" :class="stats.demo_coverage.completed ? 'success' : 'neutral'">Demo {{ stats.demo_coverage.completed }}/{{ stats.demo_coverage.total }}</span>
                  <a
                    v-if="player.live_url"
                    class="button primary small profile-live-link"
                    :href="player.live_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  ><AppIcon name="external" />进入直播间</a>
                </div>
              </div>
              <p><code>{{ player.player_id }}</code><span>{{ cupAlias }}</span></p>
            </div>
          </div>
          <div class="player-profile-proof">
            <div v-if="heroStats.length" class="player-lead-stat">
              <strong>{{ heroStats[0].value }}</strong>
              <span>PWR Rating · {{ day || '赛季总览' }}</span>
              <small v-if="heroStats[0].rank">赛季排名 #{{ heroStats[0].rank }}</small>
            </div>
            <div v-if="trophies.length" class="profile-honours">
              <span v-for="(trophy, index) in trophies" :key="index" :class="trophy.trophy">
                <AppIcon name="trophy" /><strong>{{ trophy.trophy === 'champion' ? '冠军' : '亚军' }}</strong><small>{{ trophy.day }} · {{ trophy.team_name || '暂无队名' }}</small>
              </span>
            </div>
          </div>
        </section>

        <section v-if="seasonSummary" class="panel player-season-summary" aria-labelledby="season-summary-title">
          <div v-if="seasonSummary.status === 'pending'" class="season-summary-pending" aria-live="polite">
            <span class="loader small"></span>
            <div><strong id="season-summary-title">AI 球探报告整理中</strong><p>正在根据完整赛季的有效数据生成。</p></div>
          </div>
          <template v-else>
            <div class="season-summary-heading">
              <span class="summary-kicker"><AppIcon name="activity" />DEEPSEEK SCOUTING</span>
              <span class="result-count">整季样本 · {{ seasonSummary.sample?.比赛场次 ?? stats.match_count }} 场</span>
            </div>
            <div class="season-summary-body">
              <div class="season-summary-lead">
                <h2 id="season-summary-title">{{ seasonSummary.headline }}</h2>
                <p>{{ seasonSummary.overview }}</p>
                <small v-if="seasonSummary.refreshing">数据已更新，新版报告生成中；当前展示上一版。</small>
              </div>
              <dl class="season-summary-points">
                <div><dt>优势</dt><dd>{{ seasonSummary.strength }}</dd></div>
                <div><dt>观察项</dt><dd>{{ seasonSummary.weakness }}</dd></div>
                <div><dt>打法画像</dt><dd>{{ seasonSummary.style }}</dd></div>
              </dl>
            </div>
          </template>
        </section>

        <nav class="day-navigation player-day-nav" aria-label="选手比赛日筛选">
          <span class="day-nav-label">统计范围</span>
          <div class="day-scroll">
            <router-link :to="`/player/${id}/${cup}/`" class="day-chip" :class="{ active: !day }"><span>ALL</span>赛季总览</router-link>
            <router-link v-for="(d, index) in cupDays" :key="d" :to="`/player/${id}/${cup}/${d}/`" class="day-chip" :class="{ active: d === day }">
              <span>{{ pad(index + 1) }}</span>{{ d }}
            </router-link>
          </div>
        </nav>

        <section class="player-kpi-grid" aria-label="选手核心数据">
          <article v-for="item in heroStats.slice(1)" :key="item.label">
            <span>{{ item.label }}</span><strong>{{ item.value }}</strong>
            <small v-if="item.rank">赛季排名 <b>#{{ item.rank }}</b></small><small v-else>{{ item.note }}</small>
          </article>
        </section>

        <div class="analysis-grid">
          <section class="panel chart-panel radar-panel">
            <div class="panel-header">
              <h2>能力雷达</h2>
              <span class="result-count">6 项指标</span>
            </div>
            <div ref="radarEl" class="player-chart radar-chart" role="img" :aria-label="`${playerName} 的六维能力雷达图`"></div>
          </section>
          <section class="panel chart-panel trend-panel">
            <div class="panel-header">
              <h2>Rating 走势</h2>
              <span class="result-count">{{ history.length }} 个比赛日</span>
            </div>
            <div v-if="history.length" ref="lineEl" class="player-chart line-chart" role="img" :aria-label="`${playerName} 的 Rating 走势折线图`"></div>
            <div v-else class="empty-state compact chart-empty"><span><AppIcon name="activity" /></span><h3>暂无趋势数据</h3><p>有多个比赛日后会生成走势。</p></div>
          </section>
        </div>

        <section v-if="titles.length" class="panel player-section title-profile-section">
          <div class="panel-header">
            <h2>{{ day ? '当日画像' : '赛季画像' }}</h2>
            <span class="result-count">{{ day ? '比赛日样本' : '完整赛季样本' }}</span>
          </div>
          <div class="title-showcase" :class="{ single: !secondaryTitles.length }">
            <article v-if="primaryTitle" class="title-feature">
              <span class="title-mark"><AppIcon :name="titleIcon(primaryTitle)" :size="24" /></span>
              <div class="title-feature-copy">
                <span class="title-role">主称号</span>
                <h3>{{ primaryTitle.title_name }}</h3>
                <p class="title-summary">{{ titleSummary(primaryTitle) }}</p>
                <p class="title-evidence">{{ primaryTitle.title_description }}</p>
              </div>
              <small class="title-category">{{ titleCategory(primaryTitle) }}</small>
            </article>
            <div v-if="secondaryTitles.length" class="title-support-list">
              <article v-for="title in secondaryTitles" :key="title.title_name">
                <span class="title-mark compact"><AppIcon :name="titleIcon(title)" /></span>
                <div>
                  <span class="title-category">{{ titleCategory(title) }}</span>
                  <h3>{{ title.title_name }}</h3>
                  <p>{{ titleSummary(title) }}</p>
                  <small>{{ title.title_description }}</small>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section class="panel player-section player-matches-section">
          <div class="panel-header">
            <h2>比赛记录</h2>
            <span class="result-count">{{ matchRecords.length }} 场</span>
          </div>
          <div v-if="matchRecords.length" class="table-scroll">
            <table class="data-table player-match-table">
              <thead>
                <tr>
                  <th>比赛时间</th><th>地图</th><th class="player-match-score-heading">对阵 / 比分</th><th>结果</th>
                  <th class="num">K / D / A</th><th class="num">Rating</th><th class="num">ADR</th><th class="num">KAST</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="match in matchRecords" :key="match.match_id">
                  <td class="player-match-time"><strong>{{ formatMatchDate(match) }}</strong><small>{{ formatMatchClock(match.start_time) }}</small></td>
                  <td><strong>{{ match.map_name || '未知地图' }}</strong><small>{{ match.game_mode || match.map_name_en || '—' }} · Demo {{ match.demo_analysis?.status || 'pending' }}</small></td>
                  <td class="player-match-score-cell">
                    <div class="player-match-score">
                      <span>{{ match.team1_name || '队伍 A' }}</span>
                      <strong>{{ match.team1_score ?? '—' }} : {{ match.team2_score ?? '—' }}</strong>
                      <span>{{ match.team2_name || '队伍 B' }}</span>
                    </div>
                  </td>
                  <td><span class="match-result" :class="Number(match.win) ? 'win' : 'loss'">{{ Number(match.win) ? '胜' : '负' }}</span></td>
                  <td class="num mono-data">{{ match.kill ?? 0 }} / {{ match.death ?? 0 }} / {{ match.assist ?? 0 }}</td>
                  <td class="num"><strong class="rating-value">{{ n2(match.pw_rating || match.rating) }}</strong></td>
                  <td class="num mono-data">{{ Number(match.adpr || 0).toFixed(0) }}</td>
                  <td class="num mono-data">{{ pct(match.kast_ratio) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state compact"><span><AppIcon name="database" /></span><h3>暂无比赛记录</h3><p>该统计范围内还没有可展示的逐场数据。</p></div>
        </section>

        <section class="panel player-section">
          <div class="panel-header">
            <h2>地图表现</h2>
            <span class="result-count">{{ mapStats.length }} 张地图</span>
          </div>
          <div v-if="mapStats.length" class="map-stats-grid">
            <article v-for="map in mapStats.slice(0, 6)" :key="map.map_name_en || map.map_name" class="map-stat-card">
              <div class="map-card-visual" :style="map.map_url ? { '--map-image': `url(${map.map_url})` } : {}">
                <span>{{ map.map_name_en || 'MAP' }}</span><h3>{{ map.map_name || map.map_name_en || '未知地图' }}</h3>
              </div>
              <div class="map-card-metrics">
                <div><strong>{{ map.match_count }}</strong><span>场次</span></div>
                <div><strong>{{ n2(map.avg_rating) }}</strong><span>Rating</span></div>
                <div><strong>{{ Number(map.win_rate || 0).toFixed(0) }}%</strong><span>胜率</span></div>
                <div><strong>{{ n2(map.kd_ratio) }}</strong><span>K/D</span></div>
              </div>
            </article>
          </div>
          <div v-else class="empty-state compact"><span><AppIcon name="layers" /></span><h3>暂无地图数据</h3><p>比赛完成地图关联后会显示在这里。</p></div>
        </section>

        <section class="panel player-section detailed-stats-panel">
          <div class="panel-header">
            <h2>详细数据</h2>
            <span class="result-count">{{ day || '赛季总计' }}</span>
          </div>
          <div class="detail-stat-groups">
            <article v-for="group in statGroups" :key="group.title">
              <div class="stat-group-title"><AppIcon :name="group.icon" /><h3>{{ group.title }}</h3></div>
              <dl>
                <div v-for="item in group.items" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div>
              </dl>
            </article>
          </div>
        </section>

        <section v-if="stats.demo_data" class="panel player-section detailed-stats-panel">
          <div class="panel-header">
            <div><h2>Demo 事件分析</h2><p>仅以已完成 Demo 为分母；缺失比赛不会按 0 计入。</p></div>
            <span class="result-count">覆盖 {{ stats.demo_coverage.completed }}/{{ stats.demo_coverage.total }} · v{{ stats.demo_analysis.metric_version }}</span>
          </div>
          <div class="detail-stat-groups">
            <article v-for="group in demoGroups" :key="group.title">
              <div class="stat-group-title"><AppIcon :name="group.icon" /><h3>{{ group.title }}</h3></div>
              <dl><div v-for="item in group.items" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
            </article>
          </div>
          <p class="player-update-note">Demo Rating 为实验性近似 Rating 3.0，不替代平台 PWR。</p>
        </section>

        <section v-if="killMatchups.length" class="panel player-section">
          <div class="panel-header">
            <h2>对位击杀</h2>
            <span class="result-count">按击杀次数排序</span>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead><tr><th>对手</th><th class="num">击杀次数</th></tr></thead>
              <tbody>
                <tr v-for="opponent in killMatchups.slice(0, 10)" :key="opponent.player_id">
                  <td><strong>{{ opponent.nickname || opponent.player_id }}</strong><small>{{ opponent.player_id }}</small></td>
                  <td class="num mono-data"><strong>{{ opponent.kills }}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <p v-if="lastCrawl" class="player-update-note"><AppIcon name="activity" />数据更新于 {{ formatTime(lastCrawl) }}</p>
      </template>
    </main>
    <footer class="public-footer"><router-link :to="cup ? `/${cup}/` : '/'">返回 {{ cupAlias || '赛季榜单' }}</router-link><span>PLAYER INTELLIGENCE · 熊掌CS Major</span></footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts/core'
import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, RadarComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import PerfectRankBadge from '../components/PerfectRankBadge.vue'

echarts.use([LineChart, RadarChart, GridComponent, RadarComponent, TooltipComponent, CanvasRenderer])

const route = useRoute()
const id = computed(() => route.params.id)
const cup = computed(() => route.params.cup || '')
const day = computed(() => route.params.day || '')
const player = ref(null)
const stats = ref(null)
const titles = ref([])
const trophies = ref([])
const ranks = ref({})
const cupDays = ref([])
const cupAlias = ref('')
const history = ref([])
const mapStats = ref([])
const matchRecords = ref([])
const killMatchups = ref([])
const seasonSummary = ref(null)
const lastCrawl = ref('')
const error = ref('')
const loading = ref(true)
const radarEl = ref(null)
const lineEl = ref(null)
let radarChart
let lineChart

const playerName = computed(() => player.value?.alias_name || player.value?.nickname || player.value?.player_id || '选手')
const primaryTitle = computed(() => titles.value[0] || null)
const secondaryTitles = computed(() => titles.value.slice(1, 3))
const titleCategories = {
  honour: { label: '赛季荣誉', icon: 'trophy' },
  firepower: { label: '火力特征', icon: 'target' },
  entry: { label: '突破特征', icon: 'arrowRight' },
  clutch: { label: '残局时刻', icon: 'shield' },
  teamwork: { label: '团队价值', icon: 'users' },
  consistency: { label: '赛季走势', icon: 'activity' },
  style: { label: '打法画像', icon: 'database' },
}
const heroStats = computed(() => !stats.value ? [] : [
  { label: 'PWR RATING', value: n2(stats.value.avg_pw_rating), rank: ranks.value.avg_pw_rating, featured: true },
  { label: '比赛场次', value: stats.value.match_count || 0, note: `${stats.value.win_count || 0} 场胜利` },
  { label: '胜率', value: pct(stats.value.win_rate), rank: ranks.value.win_rate },
  { label: 'K / D', value: n2(stats.value.kd_ratio), rank: ranks.value.kd_ratio },
  { label: '总击杀', value: stats.value.total_kills || 0, rank: ranks.value.total_kills },
  { label: 'MVP', value: stats.value.total_mvp || 0, rank: ranks.value.total_mvp },
])
const statGroups = computed(() => {
  const s = stats.value || {}
  return [
    { title: '基础数据', icon: 'activity', items: [
      { label: '比赛场次', value: s.match_count || 0 }, { label: '胜场', value: s.win_count || 0 }, { label: '胜率', value: pct(s.win_rate) },
      { label: '总回合', value: s.total_rounds || 0 }, { label: '每回合击杀', value: n2(s.kills_per_round) }, { label: '每回合死亡', value: n2(s.deaths_per_round) },
      { label: '每回合助攻', value: n2(s.assists_per_round) }, { label: '总击杀', value: s.total_kills || 0 }, { label: '总助攻', value: s.total_assists || 0 },
    ] },
    { title: '击杀效率', icon: 'target', items: [
      { label: '首杀 / 首死', value: `${s.total_first_kills || 0} / ${s.total_first_deaths || 0}` }, { label: 'FK / FD', value: n2(s.fk_fd_ratio) },
      { label: '开局对枪胜率', value: pct(s.opening_duel_win_rate) }, { label: '开局对枪/回合', value: n2(s.opening_duels_per_round) },
      { label: '爆头数', value: s.total_headshots || 0 }, { label: '爆头率', value: pct(s.avg_headshot_ratio) }, { label: 'K / D', value: n2(s.kd_ratio) },
    ] },
    { title: '多杀与残局', icon: 'trophy', items: [
      { label: '2K / 3K', value: `${s.total_2k || 0} / ${s.total_3k || 0}` }, { label: '4K / 5K', value: `${s.total_4k || 0} / ${s.total_5k || 0}` },
      { label: '多杀回合', value: s.multi_kill_rounds || 0 }, { label: '多杀回合率', value: pct(s.multi_kill_round_rate) },
      { label: '1V1 / 1V2', value: `${s.total_1v1 || 0} / ${s.total_1v2 || 0}` }, { label: '1V3 / 1V4 / 1V5', value: `${s.total_1v3 || 0} / ${s.total_1v4 || 0} / ${s.total_1v5 || 0}` },
    ] },
    { title: '高级数据', icon: 'database', items: [
      { label: 'PWR Rating', value: n2(s.avg_pw_rating) }, { label: 'RWS', value: n2(s.avg_rws) }, { label: 'WE', value: n2(s.avg_we) },
      { label: 'ADR（回合加权）', value: n2(s.avg_adpr) }, { label: 'KAST', value: pct(s.avg_kast) }, { label: '比赛 MVP', value: s.match_mvp_count || 0 },
      { label: 'MVP 场次占比', value: pct(s.mvp_match_rate) }, { label: '狙击击杀', value: s.total_snipe_num || 0 },
    ] },
    { title: '投掷物', icon: 'layers', items: [
      { label: '敌方致盲', value: s.total_flash_success || 0 }, { label: '敌方致盲/回合', value: n2(s.enemy_flashes_per_round) },
      { label: '队友致盲', value: s.total_flash_teammate || 0 }, { label: '队友致盲占比', value: pct(s.team_flash_share) },
      { label: '投掷物总数', value: s.total_throws_count || 0 }, { label: '投掷物/回合', value: n2(s.throws_per_round) },
      { label: '手雷伤害', value: s.total_grenade_damage || 0 }, { label: '燃烧伤害', value: s.total_inferno_damage || 0 },
      { label: '道具伤害/回合', value: n2(s.utility_damage_per_round) },
    ] },
    { title: '团队协作', icon: 'users', items: [
      { label: '补枪击杀', value: s.total_trade_frags || 0 }, { label: '补枪击杀占比', value: pct(s.trade_kill_share) },
      { label: '总道具伤害', value: s.total_utility_damage || 0 },
    ] },
  ]
})
const demoGroups = computed(() => {
  const s = stats.value?.demo_data || {}
  return [
    { title: '闪光质量', icon: 'layers', items: [
      { label: '闪光投掷', value: s.flash_thrown || 0 }, { label: '敌方致盲事件', value: s.enemies_flashed || 0 },
      { label: '去重敌方致盲时长', value: `${n2(s.enemy_flash_seconds)}s` }, { label: '平均敌方致盲', value: `${n2(s.average_enemy_flash_seconds)}s` },
      { label: '每颗闪光致盲敌人', value: n2(s.enemies_per_flash) }, { label: '队友致盲占比', value: pct(s.team_flash_share) },
      { label: '闪光助攻', value: s.flash_assists || 0 },
    ] },
    { title: '道具效率', icon: 'database', items: [
      { label: '投掷物', value: s.grenades_thrown || 0 }, { label: 'HE / 烟 / 火', value: `${s.he_thrown || 0} / ${s.smoke_thrown || 0} / ${(s.molotov_thrown || 0) + (s.incendiary_thrown || 0)}` },
      { label: 'HE / 火焰伤害', value: `${s.he_damage || 0} / ${s.fire_damage || 0}` }, { label: '道具伤害/投掷', value: n2(s.utility_damage_per_throw) },
      { label: '阵亡未用道具价值', value: `$${s.unused_utility_value || 0}` },
    ] },
    { title: '事件与协作', icon: 'users', items: [
      { label: '补枪击杀', value: s.total_trade_frags || 0 }, { label: '被补枪死亡', value: s.total_deaths_traded || 0 },
      { label: '被补枪率', value: pct(s.death_trade_rate) }, { label: '残局胜利', value: s.total_clutches_won || 0 },
      { label: '开局击杀转回合胜率', value: pct(s.opening_round_conversion) }, { label: '队友击杀', value: s.total_team_kills || 0 },
    ] },
    { title: '分边表现', icon: 'activity', items: [
      { label: 'CT / T 回合', value: `${s.ct_rounds || 0} / ${s.t_rounds || 0}` }, { label: 'CT / T 击杀', value: `${s.ct_kills || 0} / ${s.t_kills || 0}` },
      { label: 'CT / T ADR', value: `${n2(s.ct_adr)} / ${n2(s.t_adr)}` }, { label: 'CT / T KAST', value: `${pct(s.ct_kast)} / ${pct(s.t_kast)}` },
    ] },
    { title: '实验性 Rating', icon: 'target', items: [
      { label: 'Demo Rating', value: n2(s.demo_rating) }, { label: '击杀 / 伤害', value: `${n2(s.rating_kills)} / ${n2(s.rating_damage)}` },
      { label: '生存 / eKAST', value: `${n2(s.rating_survival)} / ${n2(s.rating_kast)}` }, { label: '多杀 / 回合影响', value: `${n2(s.rating_multi_kill)} / ${n2(s.rating_round_swing)}` },
    ] },
  ]
})

function n2(value) { return Number(value || 0).toFixed(2) }
function pct(value) { return `${(Number(value || 0) * 100).toFixed(1)}%` }
function titleMeta(title) { return titleCategories[title?.title_category] || { label: '赛季画像', icon: 'activity' } }
function titleCategory(title) { return titleMeta(title).label }
function titleIcon(title) { return titleMeta(title).icon }
function titleSummary(title) { return title?.title_summary || '由本赛季有效样本计算得出' }
function normalizeRatio(value) { const number = Number(value || 0); return number > 1 ? number : number * 100 }
function pad(value) { return String(value || 0).padStart(2, '0') }
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 16) : '' }
function formatMatchDate(match) {
  const raw = String(match?.play_day || '').replace(/\D/g, '')
  if (raw.length === 8) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
  return formatTime(match?.start_time).slice(0, 10) || '—'
}
function formatMatchClock(value) {
  const text = formatTime(value)
  return text.length >= 16 ? text.slice(11, 16) : '时间未知'
}
function uniqueTitles(list) {
  const seen = new Set()
  return (list || []).filter((title) => {
    if (seen.has(title.title_name)) return false
    seen.add(title.title_name)
    return true
  })
}
function chartTokens() {
  const styles = getComputedStyle(document.documentElement)
  const read = (name) => styles.getPropertyValue(name).trim()
  return {
    ink: read('--color-accent-ink'),
    tooltip: read('--color-ink'),
    text: read('--color-muted'),
    paper: read('--color-paper'),
    paper2: read('--color-paper-2'),
    paper3: read('--color-paper-3'),
    rule: read('--color-rule'),
    accent: read('--color-accent'),
    fill: read('--color-chart-fill'),
    fade: read('--color-chart-fade'),
    font: read('--font-body'),
  }
}
function chartTextStyle(size = 11, colors = chartTokens()) { return { color: colors.text, fontSize: size, fontFamily: colors.font } }
function drawCharts() {
  const colors = chartTokens()
  if (radarEl.value && stats.value) {
    radarChart = radarChart || echarts.init(radarEl.value)
    radarChart.setOption({
      animationDuration: 500,
      tooltip: { trigger: 'item', backgroundColor: colors.tooltip, borderWidth: 0, textStyle: { color: colors.ink } },
      radar: {
        radius: '66%', center: ['50%', '53%'], splitNumber: 4,
        indicator: [
          { name: 'Rating', max: 2 }, { name: 'K/D', max: 2 }, { name: 'ADPR', max: 150 },
          { name: 'KAST', max: 100 }, { name: 'HS%', max: 100 }, { name: '胜率', max: 100 },
        ],
        axisName: chartTextStyle(11, colors), splitArea: { areaStyle: { color: [colors.paper2, colors.paper] } },
        splitLine: { lineStyle: { color: colors.rule } }, axisLine: { lineStyle: { color: colors.rule } },
      },
      series: [{ type: 'radar', symbol: 'circle', symbolSize: 5, lineStyle: { color: colors.accent, width: 2 }, itemStyle: { color: colors.accent }, areaStyle: { color: colors.fill }, data: [{ name: playerName.value, value: [stats.value.avg_pw_rating || 0, stats.value.kd_ratio || 0, stats.value.avg_adpr || 0, normalizeRatio(stats.value.avg_kast), normalizeRatio(stats.value.avg_headshot_ratio), normalizeRatio(stats.value.win_rate)] }] }],
    })
  }
  if (lineEl.value && history.value.length) {
    lineChart = lineChart || echarts.init(lineEl.value)
    lineChart.setOption({
      animationDuration: 500,
      grid: { left: 42, right: 18, top: 28, bottom: 34 },
      tooltip: { trigger: 'axis', backgroundColor: colors.tooltip, borderWidth: 0, textStyle: { color: colors.ink } },
      xAxis: { type: 'category', boundaryGap: false, data: history.value.map((item) => item.day), axisLabel: chartTextStyle(10, colors), axisLine: { lineStyle: { color: colors.rule } }, axisTick: { show: false } },
      yAxis: { type: 'value', scale: true, splitNumber: 4, axisLabel: chartTextStyle(10, colors), splitLine: { lineStyle: { color: colors.paper3 } } },
      series: [{ type: 'line', data: history.value.map((item) => Number(item.data.avg_pw_rating || 0).toFixed(2)), smooth: 0.28, showSymbol: true, symbolSize: 6, lineStyle: { color: colors.accent, width: 2.5 }, itemStyle: { color: colors.accent, borderColor: colors.paper2, borderWidth: 2 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: colors.fill }, { offset: 1, color: colors.fade }] } } }],
    })
  }
}
function resizeCharts() { radarChart?.resize(); lineChart?.resize() }
async function load() {
  radarChart?.dispose()
  lineChart?.dispose()
  radarChart = null
  lineChart = null
  error.value = ''
  loading.value = true
  try {
    const data = await api.player(id.value, cup.value, day.value || null)
    player.value = data.player
    stats.value = data.player_data
    titles.value = uniqueTitles(data.titles)
    trophies.value = data.trophy_history || []
    ranks.value = data.player_rankings || {}
    cupDays.value = data.cup_days || []
    cupAlias.value = data.cup_alias || data.cup
    history.value = data.historical_data || []
    mapStats.value = data.map_stats || []
    matchRecords.value = data.match_records || []
    killMatchups.value = data.kill_matchups || []
    seasonSummary.value = data.season_summary || null
    lastCrawl.value = data.last_crawl_time || ''
    document.title = `${playerName.value} · ${cupAlias.value} · 熊掌CS Major`
    loading.value = false
    await nextTick()
    drawCharts()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => { load(); window.addEventListener('resize', resizeCharts) })
watch(() => [route.params.id, route.params.cup, route.params.day], load)
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  radarChart?.dispose()
  lineChart?.dispose()
})
</script>
