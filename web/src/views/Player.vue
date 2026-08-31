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
                  <a
                    v-if="player.live_url"
                    class="button primary small profile-live-link"
                    :href="player.live_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  ><AppIcon name="external" />进入直播间</a>
                </div>
              </div>
              <p><span>{{ cupAlias }}</span></p>
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
                  <th class="num">K / D / A</th><th class="num">Rating</th><th class="num">ADR</th><th class="num">KAST</th><th class="player-match-open-heading"><span class="sr-only">查看详情</span></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="match in matchRecords"
                  :key="match.match_id"
                  class="player-match-row"
                  tabindex="0"
                  title="查看比赛详情"
                  @click="openMatch(match)"
                  @keydown.enter.prevent="openMatch(match)"
                  @keydown.space.prevent="openMatch(match)"
                >
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
                  <td class="player-match-open">
                    <button class="button text-button small" type="button" :aria-label="`查看 ${match.map_name || '比赛'} 详情`" @click.stop="openMatch(match)">
                      详情<AppIcon name="chevronRight" />
                    </button>
                  </td>
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
            <div><h2>高级分析数据</h2><p>基于已完成比赛；次数类指标展示场均，效率类指标按实际回合或事件计算。</p></div>
            <span class="result-count">已分析 {{ stats.demo_coverage.completed }}/{{ stats.demo_coverage.total }} 场</span>
          </div>
          <div class="detail-stat-groups">
            <article v-for="group in demoGroups" :key="group.title">
              <div class="stat-group-title"><AppIcon :name="group.icon" /><h3>{{ group.title }}</h3></div>
              <dl><div v-for="item in group.items" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
            </article>
          </div>
          <p class="player-update-note">高级 Rating 为实验性估算值，按回合加权计算，不替代平台 PWR。</p>
        </section>

        <section v-if="sortedSoftMatchups.length" class="panel player-section soft-targets-section" aria-labelledby="soft-targets-title">
          <div class="panel-header">
            <div>
              <span class="summary-kicker"><AppIcon name="target" />KILL MATCHUPS</span>
              <h2 id="soft-targets-title">软柿子 · TOP 3</h2>
              <p>只统计双向击杀合计超过 5 次且对位比大于 1 的对位；不足 3 人时不补位。</p>
            </div>
            <div class="matchup-sorter" aria-label="软柿子排序方式">
              <button type="button" :class="{ active: matchupSort === 'ratio' }" @click="matchupSort = 'ratio'">按对位比</button>
              <button type="button" :class="{ active: matchupSort === 'kills' }" @click="matchupSort = 'kills'">按击杀数</button>
            </div>
          </div>
          <ol class="soft-target-podium">
            <li v-for="(opponent, index) in softTargets" :key="opponent.player_id" :class="`place-${index + 1}`">
              <span class="target-rank">#{{ index + 1 }}</span>
              <span class="target-sight" aria-hidden="true"><AppIcon name="target" :size="24" /></span>
              <div class="target-copy">
                <small>{{ softTargetLabel(index) }}</small>
                <strong>{{ opponent.nickname || opponent.player_id }}</strong>
                <code>{{ opponent.player_id }}</code>
              </div>
              <div class="target-kills">
                <strong>{{ matchupSort === 'ratio' ? formatMatchupRatio(opponent) : opponent.kills }}</strong>
                <span>{{ opponent.kills }} 杀 / {{ opponent.deaths }} 被杀</span>
              </div>
            </li>
          </ol>
          <div v-if="otherMatchups.length" class="table-scroll soft-target-overflow">
            <table class="data-table">
              <thead><tr><th>其他对位</th><th class="num">对位 K:D</th><th class="num">对位比</th></tr></thead>
              <tbody>
                <tr v-for="opponent in otherMatchups" :key="opponent.player_id">
                  <td><strong>{{ opponent.nickname || opponent.player_id }}</strong><small>{{ opponent.player_id }}</small></td>
                  <td class="num mono-data"><strong>{{ opponent.kills }} : {{ opponent.deaths }}</strong></td>
                  <td class="num mono-data"><strong>{{ formatMatchupRatio(opponent) }}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="hardTargets.length" class="panel player-section soft-targets-section hard-targets-section" aria-labelledby="hard-targets-title">
          <div class="panel-header">
            <div>
              <span class="summary-kicker"><AppIcon name="shield" />TOUGH MATCHUPS</span>
              <h2 id="hard-targets-title">尿完了 · TOP 3</h2>
              <p>同样只统计双向击杀合计超过 5 次的对位，按对位比从低到高排列。</p>
            </div>
          </div>
          <ol class="soft-target-podium hard-target-podium">
            <li v-for="(opponent, index) in hardTargets" :key="opponent.player_id" :class="`place-${index + 1}`">
              <span class="target-rank">#{{ index + 1 }}</span>
              <span class="target-sight" aria-hidden="true"><AppIcon name="shield" :size="24" /></span>
              <div class="target-copy">
                <small>{{ hardTargetLabel(index) }}</small>
                <strong>{{ opponent.nickname || opponent.player_id }}</strong>
                <code>{{ opponent.player_id }}</code>
              </div>
              <div class="target-kills">
                <strong>{{ formatMatchupRatio(opponent) }}</strong>
                <span>{{ opponent.kills }} 杀 / {{ opponent.deaths }} 被杀</span>
              </div>
            </li>
          </ol>
        </section>

        <section v-if="rankHistory.length" class="panel player-section chart-panel ladder-trend-panel">
          <div class="panel-header">
            <h2>天梯分走势</h2>
            <span class="result-count">{{ rankHistory.length }} 次采样</span>
          </div>
          <div ref="rankLineEl" class="player-chart line-chart" role="img" :aria-label="`${playerName} 的天梯分走势折线图`"></div>
        </section>

        <p v-if="lastCrawl" class="player-update-note"><AppIcon name="activity" />数据更新于 {{ formatTime(lastCrawl) }}</p>
      </template>
    </main>

    <AppModal
      :open="matchDetailOpen"
      :title="matchDetailTitle"
      eyebrow="MATCH REPORT"
      :description="matchDetailSubtitle"
      size="wide"
      @close="closeMatch"
    >
      <div v-if="matchDetail" class="match-detail public-match-detail">
        <section
          class="match-scoreboard"
          :style="matchDetail.map_url ? { '--map-image': `url(${matchDetail.map_url})` } : {}"
        >
          <div class="scoreboard-meta">
            <span>{{ matchDetail.map_name_en || matchDetail.game_mode || 'MATCH' }}</span>
            <span>{{ cupAlias || cup }}</span>
          </div>
          <div class="scoreboard-line">
            <div class="scoreboard-team">
              <span>{{ matchDetail.team1_name || '队伍 A' }}</span>
              <small v-if="Number(matchDetail.win_team) === 1">胜方</small>
            </div>
            <strong class="scoreboard-score">{{ matchDetail.team1_score ?? '—' }} : {{ matchDetail.team2_score ?? '—' }}</strong>
            <div class="scoreboard-team away">
              <span>{{ matchDetail.team2_name || '队伍 B' }}</span>
              <small v-if="Number(matchDetail.win_team) === 2">胜方</small>
            </div>
          </div>
          <p class="scoreboard-footnote">
            {{ matchDetail.map_name || '未知地图' }} · {{ matchDetail.game_mode || '未知模式' }}
            <template v-if="matchDetail.team1_half_score != null || matchDetail.team2_half_score != null">
              · 半场 {{ matchDetail.team1_half_score ?? '—' }}:{{ matchDetail.team2_half_score ?? '—' }}
            </template>
            <template v-if="matchDetail.team1_extra_score || matchDetail.team2_extra_score">
              · 加时 {{ matchDetail.team1_extra_score ?? 0 }}:{{ matchDetail.team2_extra_score ?? 0 }}
            </template>
          </p>
        </section>

        <div class="match-detail-facts">
          <div><span>比赛日</span><strong>{{ formatPlayDay(matchDetail.play_day) }}</strong></div>
          <div><span>开赛时间</span><strong>{{ formatDateTime(matchDetail.start_time) }}</strong></div>
          <div><span>比赛时长</span><strong>{{ formatDuration(matchDetail.duration) }}</strong></div>
          <div><span>比赛模式</span><strong>{{ matchDetail.game_mode || '—' }}</strong></div>
        </div>

        <div v-if="matchDetailLoading" class="loading-state compact"><span class="loader"></span><p>正在读取比赛详情…</p></div>
        <div v-else-if="matchDetailError" class="inline-alert error" role="alert">
          <AppIcon name="alert" />
          <span><strong>无法读取比赛详情</strong>{{ matchDetailError }}</span>
        </div>
        <template v-else>
          <section v-for="board in matchTeamBoards" :key="board.team" class="team-board" :class="{ winner: board.winner }">
            <div class="team-board-header">
              <div><h3>{{ board.name }}</h3><small>{{ board.players.length }} 名选手{{ board.winner ? ' · 胜方' : '' }}</small></div>
              <strong>{{ board.score ?? '—' }}</strong>
            </div>
            <div class="table-scroll">
              <table class="data-table scoreboard-table">
                <thead>
                  <tr>
                    <th>选手</th><th class="num">K</th><th class="num">D</th><th class="num">A</th><th class="num">+/-</th>
                    <th class="num">ADR</th><th class="num">Rating</th><th class="num">KAST</th><th class="num">HS%</th><th class="num">FK</th><th>MVP</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in board.players" :key="p.player_id" :class="{ mvp: p.mvp, 'current-player': String(p.player_id) === String(player?.player_id) }">
                    <td>
                      <div class="identity-cell">
                        <img v-if="p.avatar" class="player-monogram small match-avatar" :src="avatarUrl(p.avatar)" :alt="`${matchPlayerName(p)} 头像`">
                        <span v-else class="player-monogram small">{{ matchPlayerName(p).slice(0, 1).toUpperCase() }}</span>
                        <span><strong>{{ matchPlayerName(p) }}</strong><small v-if="String(p.player_id) === String(player?.player_id)">当前选手</small></span>
                      </div>
                    </td>
                    <td class="num">{{ p.kill ?? 0 }}</td>
                    <td class="num">{{ p.death ?? 0 }}</td>
                    <td class="num">{{ p.assist ?? 0 }}</td>
                    <td class="num" :class="diffClass(p)">{{ formatDiff(p) }}</td>
                    <td class="num">{{ formatStat(p.adpr, 0) }}</td>
                    <td class="num rating-cell">{{ formatStat(p.pw_rating || p.rating, 2) }}</td>
                    <td class="num">{{ formatDetailRatio(p.kast_ratio) }}</td>
                    <td class="num">{{ formatDetailRatio(p.headshot_ratio) }}</td>
                    <td class="num">{{ p.entry_kill ?? 0 }}</td>
                    <td>{{ p.mvp ? 'MVP' : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <div v-if="!matchTeamBoards.length" class="empty-state compact"><span><AppIcon name="database" /></span><h3>暂无选手数据</h3><p>这场比赛暂时没有可展示的详细数据。</p></div>
        </template>
      </div>
    </AppModal>

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
import { api, avatarUrl } from '../api'
import AppModal from '../components/AppModal.vue'
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
const rankHistory = ref([])
const mapStats = ref([])
const matchRecords = ref([])
const killMatchups = ref([])
const matchupSort = ref('ratio')
const seasonSummary = ref(null)
const matchDetailOpen = ref(false)
const matchDetail = ref(null)
const matchDetailLoading = ref(false)
const matchDetailError = ref('')
const lastCrawl = ref('')
const error = ref('')
const loading = ref(true)
const radarEl = ref(null)
const lineEl = ref(null)
const rankLineEl = ref(null)
let radarChart
let lineChart
let rankLineChart
let matchDetailRequest = 0

const playerName = computed(() => player.value?.alias_name || player.value?.nickname || player.value?.player_id || '选手')
const matchDetailTitle = computed(() => matchDetail.value?.map_name || '比赛详情')
const matchDetailSubtitle = computed(() => {
  if (!matchDetail.value) return '查看双方选手的当场数据。'
  return [formatPlayDay(matchDetail.value.play_day), formatMatchClock(matchDetail.value.start_time)].filter((item) => item && item !== '—' && item !== '时间未知').join(' · ')
})
const matchTeamBoards = computed(() => {
  const match = matchDetail.value
  if (!match) return []
  const grouped = { 1: [], 2: [], other: [] }
  for (const matchPlayer of match.players || []) {
    const team = Number(matchPlayer.team)
    if (team === 1 || team === 2) grouped[team].push(matchPlayer)
    else grouped.other.push(matchPlayer)
  }
  const sorted = (list) => [...list].sort((a, b) => Number(b.pw_rating || b.rating || 0) - Number(a.pw_rating || a.rating || 0))
  const boards = [
    { team: 1, name: match.team1_name || '队伍 A', score: match.team1_score, winner: Number(match.win_team) === 1, players: sorted(grouped[1]) },
    { team: 2, name: match.team2_name || '队伍 B', score: match.team2_score, winner: Number(match.win_team) === 2, players: sorted(grouped[2]) },
  ]
  if (grouped.other.length) boards.push({ team: 0, name: '未分队', score: null, winner: false, players: sorted(grouped.other) })
  return boards.filter((board) => board.players.length)
})
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
const validMatchups = computed(() => killMatchups.value.filter((opponent) => (
  Number(opponent.encounters ?? (Number(opponent.kills || 0) + Number(opponent.deaths || 0))) > 5
)))
const sortedSoftMatchups = computed(() => validMatchups.value
  .filter((opponent) => matchupRatio(opponent) > 1)
  .sort((a, b) => {
  if (matchupSort.value === 'kills') {
    return Number(b.kills || 0) - Number(a.kills || 0)
      || Number(a.deaths || 0) - Number(b.deaths || 0)
  }
  return matchupRatio(b) - matchupRatio(a)
    || Number(b.encounters || 0) - Number(a.encounters || 0)
    || Number(b.kills || 0) - Number(a.kills || 0)
  }))
const softTargets = computed(() => sortedSoftMatchups.value.slice(0, 3))
const otherMatchups = computed(() => sortedSoftMatchups.value.slice(3, 10))
const hardTargets = computed(() => [...validMatchups.value].sort((a, b) => (
  matchupRatio(a) - matchupRatio(b)
  || Number(b.encounters || 0) - Number(a.encounters || 0)
  || Number(b.deaths || 0) - Number(a.deaths || 0)
)).slice(0, 3))
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
      { label: '场均闪光投掷', value: n2(s.avg_flash_thrown_per_match) }, { label: '场均敌方致盲', value: n2(s.avg_enemies_flashed_per_match) },
      { label: '平均单次致盲', value: `${n2(s.average_enemy_flash_seconds)}s` },
      { label: '每颗闪光致盲敌人', value: n2(s.enemies_per_flash) }, { label: '队友致盲占比', value: pct(s.team_flash_share) },
      { label: '场均闪光助攻', value: n2(s.avg_flash_assists_per_match) },
    ] },
    { title: '道具效率', icon: 'database', items: [
      { label: '场均投掷物', value: n2(s.avg_grenades_thrown_per_match) }, { label: '场均 HE / 烟 / 火', value: `${n2(s.avg_he_thrown_per_match)} / ${n2(s.avg_smoke_thrown_per_match)} / ${n2(s.avg_fire_thrown_per_match)}` },
      { label: '道具伤害/回合', value: n2(s.utility_damage_per_round) }, { label: '道具伤害/投掷', value: n2(s.utility_damage_per_throw) },
      { label: '场均未用道具价值', value: `$${n2(s.avg_unused_utility_value_per_match)}` },
    ] },
    { title: '事件与协作', icon: 'users', items: [
      { label: '场均补枪击杀', value: n2(s.avg_trade_frags_per_match) }, { label: '场均被补枪死亡', value: n2(s.avg_deaths_traded_per_match) },
      { label: '被补枪率', value: pct(s.death_trade_rate) }, { label: '场均残局胜利', value: n2(s.avg_clutches_won_per_match) },
      { label: '开局击杀转回合胜率', value: pct(s.opening_round_conversion) }, { label: '场均队友击杀', value: n2(s.avg_team_kills_per_match) },
    ] },
    { title: '分边表现', icon: 'activity', items: [
      { label: 'CT / T 样本回合', value: `${s.ct_rounds || 0} / ${s.t_rounds || 0}` }, { label: 'CT / T 每回合击杀', value: `${n2(s.ct_kills_per_round)} / ${n2(s.t_kills_per_round)}` },
      { label: 'CT / T ADR', value: `${n2(s.ct_adr)} / ${n2(s.t_adr)}` }, { label: 'CT / T KAST', value: `${pct(s.ct_kast)} / ${pct(s.t_kast)}` },
    ] },
    { title: '回合加权 Rating', icon: 'target', items: [
      { label: '高级 Rating', value: n2(s.demo_rating) }, { label: '击杀 / 伤害', value: `${n2(s.rating_kills)} / ${n2(s.rating_damage)}` },
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
function softTargetLabel(index) { return ['头号软柿子', '顺手目标', '稳定提款机'][index] || '对位目标' }
function hardTargetLabel(index) { return ['一滴不剩', '快见底了', '还剩两滴'][index] || '棘手对位' }
function matchupRatio(opponent) {
  return Number(opponent?.deaths || 0) === 0
    ? Number.POSITIVE_INFINITY
    : Number(opponent?.kills || 0) / Number(opponent.deaths)
}
function formatMatchupRatio(opponent) {
  return Number(opponent?.deaths || 0) === 0
    ? '∞'
    : Number(opponent?.kill_death_ratio || 0).toFixed(2)
}
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
function formatPlayDay(value) {
  const raw = String(value || '').replace(/\D/g, '')
  if (raw.length === 8) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
  return value || '—'
}
function formatDateTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '—'
}
function formatRankSample(value) {
  const text = formatTime(value)
  return text ? `${text.slice(5, 10)} ${text.slice(11, 16)}` : ''
}
function formatDuration(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '—'
  if (number < 180) return `${Math.round(number)} 分钟`
  const total = Math.round(number)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  return hours ? `${hours} 小时 ${minutes} 分钟` : `${minutes} 分钟`
}
function matchPlayerName(matchPlayer) {
  return matchPlayer?.alias_name || matchPlayer?.nickname || '未知选手'
}
function formatStat(value, digits = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '—'
}
function formatDetailRatio(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${Math.round(number <= 1 ? number * 100 : number)}%`
}
function formatDiff(matchPlayer) {
  const diff = Number(matchPlayer?.kill || 0) - Number(matchPlayer?.death || 0)
  return diff > 0 ? `+${diff}` : String(diff)
}
function diffClass(matchPlayer) {
  const diff = Number(matchPlayer?.kill || 0) - Number(matchPlayer?.death || 0)
  if (diff > 0) return 'positive'
  if (diff < 0) return 'negative'
  return ''
}
async function openMatch(match) {
  if (!match?.match_id || !cup.value) return
  const requestId = ++matchDetailRequest
  matchDetailOpen.value = true
  matchDetail.value = match
  matchDetailLoading.value = true
  matchDetailError.value = ''
  try {
    const detail = await api.match(match.match_id, cup.value)
    if (requestId === matchDetailRequest) matchDetail.value = detail
  } catch (e) {
    if (requestId === matchDetailRequest) matchDetailError.value = e.message
  } finally {
    if (requestId === matchDetailRequest) matchDetailLoading.value = false
  }
}
function closeMatch() {
  matchDetailRequest += 1
  matchDetailOpen.value = false
  matchDetail.value = null
  matchDetailLoading.value = false
  matchDetailError.value = ''
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
  if (rankLineEl.value && rankHistory.value.length) {
    rankLineChart = rankLineChart || echarts.init(rankLineEl.value)
    rankLineChart.setOption({
      animation: false,
      grid: { left: 54, right: 22, top: 28, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: colors.tooltip,
        borderWidth: 0,
        textStyle: { color: colors.ink },
        formatter: (items) => {
          const sample = rankHistory.value[items?.[0]?.dataIndex]
          return sample ? `${formatDateTime(sample.sampled_at)}<br>${sample.level} ${sample.score}` : ''
        },
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: rankHistory.value.map((item) => item.sampled_at),
        axisLabel: { ...chartTextStyle(10, colors), formatter: formatRankSample },
        axisLine: { lineStyle: { color: colors.rule } },
        axisTick: { show: false },
      },
      yAxis: { type: 'value', scale: true, splitNumber: 4, axisLabel: chartTextStyle(10, colors), splitLine: { lineStyle: { color: colors.paper3 } } },
      series: [{
        type: 'line',
        data: rankHistory.value.map((item) => Number(item.score || 0)),
        smooth: 0.2,
        showSymbol: rankHistory.value.length < 20,
        symbolSize: 5,
        lineStyle: { color: colors.accent, width: 2 },
        itemStyle: { color: colors.accent },
      }],
    })
  }
}
function resizeCharts() { radarChart?.resize(); lineChart?.resize(); rankLineChart?.resize() }
async function load() {
  closeMatch()
  matchupSort.value = 'ratio'
  radarChart?.dispose()
  lineChart?.dispose()
  rankLineChart?.dispose()
  radarChart = null
  lineChart = null
  rankLineChart = null
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
    // 日期导航保持新到旧；走势图按时间从左到右推进。
    history.value = [...(data.historical_data || [])].sort((a, b) =>
      String(a.day || '').localeCompare(String(b.day || '')),
    )
    rankHistory.value = data.perfect_rank_history || []
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
  rankLineChart?.dispose()
})
</script>
